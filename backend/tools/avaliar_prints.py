"""Mede a leitura de prints contra os prints sintéticos (fatia 9, ADR-0023).

    cd backend
    uv run python -m tools.gerar_prints      # uma vez: desenha os PNGs
    uv run python -m tools.avaliar_prints                    # calibração; custa centavos
    uv run python -m tools.avaliar_prints --divisao teste    # a medida limpa, uma vez só

NÃO roda no CI: chama a Anthropic com a chave do `.env` da raiz, pelo mesmo `Settings` da
aplicação, sem imprimi-la. Em série, como em produção.

Para cada print, imita o frontend (redução às dimensões da Anthropic e JPEG de qualidade 0,9),
passa pela validação do backend, pela leitura e pelo MESMO caminho do texto. E roda o texto do
mesmo caso pelo caminho do texto, para comparar. Relata, só por id — nem a mensagem, nem a
transcrição, nem a saída da IA vão para o relatório:

- taxa de erro por caractere (CER) da transcrição contra o texto que o script desenhou;
- acerto de cada campo do contexto contra o que o script desenhou;
- concordância do nível imagem contra texto do mesmo caso (motor e final);
- os borrados caindo no plano B; as injeções pegas pelo motor;
- latência (p50, p95, máxima) e custo;
- quantas explicações citam um aplicativo pelo nome sem a leitura ter identificado o canal.

Antes, confere uma vez se o modelo é da camada de alta resolução: `count_tokens` (gratuito) com
`transformations.oversized_image: "error"` num print de 1170 por 2532. Na camada padrão ele seria
recusado.
"""

import argparse
import asyncio
import base64
import io
import logging
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from PIL import Image

from app.analyzers.urls import URLExtractor
from app.api.deps import obter_servico_analise
from app.formulator.analisador import AnalisadorIA
from app.formulator.cliente import ClienteAnthropic, RespostaIA
from app.formulator.prompt import EntradaIA, PrintParaIA
from app.ocr.imagem import preparar_imagem, tamanho_alvo
from app.ocr.leitura import LeitorDePrint, LeituraFalhou, texto_do_print
from app.schemas.analise import NivelRisco
from app.scoring.combinacao import combinar
from app.scoring.regras import carregar_regras
from tools.avaliar_corpus import (
    PASTA_RELATORIOS,
    RAIZ,
    Caso,
    _commit,
    carregar_corpus,
    hash_do_corpus,
    percentil,
)
from tools.gerar_prints import (
    LISTA,
    PASTA_PRINTS,
    SEMENTE_PRINTS,
    carregar_lista,
    gabarito_do_contexto,
    mensagens_esperadas,
    texto_esperado_da_leitura,
)
from tools.sortear_divisao import PASTA_CASOS
from tools.testar_ia import PRECO_ENTRADA, PRECO_SAIDA, MotivoDoPlanoB

# Nomes que a explicação não deve usar quando a leitura não disse qual é o aplicativo.
APLICATIVOS = ("whatsapp", "instagram", "telegram", "messenger", "facebook")
CAMPOS = ("canal", "remetente_salvo", "aviso_do_app", "primeira_mensagem", "tem_link_visivel")
_ORDEM: dict[NivelRisco, int] = {"BAIXO": 0, "MEDIO": 1, "ALTO": 2}


def taxa_de_erro_por_caractere(lido: str, esperado: str) -> float:
    """Distância de Levenshtein ÷ tamanho do esperado, com os espaços normalizados (quebra de
    linha e espaço duplo não são erro de leitura). Programação dinâmica, uma linha por vez."""
    a = re.sub(r"\s+", " ", lido).strip()
    b = re.sub(r"\s+", " ", esperado).strip()
    if not b:
        return 0.0 if not a else 1.0
    anterior = list(range(len(b) + 1))
    for i, letra_a in enumerate(a, start=1):
        atual = [i]
        for j, letra_b in enumerate(b, start=1):
            atual.append(
                min(
                    anterior[j] + 1,  # apagar
                    atual[j - 1] + 1,  # inserir
                    anterior[j - 1] + (letra_a != letra_b),  # trocar
                )
            )
        anterior = atual
    return anterior[-1] / len(b)


class ClienteQueContaTudo:
    """Repassa ao cliente real e guarda os tokens da última leitura e da última análise."""

    def __init__(self, cliente: ClienteAnthropic) -> None:
        self._cliente = cliente
        self.leitura: RespostaIA | None = None
        self.analise: RespostaIA | None = None

    async def gerar(self, sistema: str, entrada: str) -> RespostaIA:
        self.analise = None
        self.analise = await self._cliente.gerar(sistema, entrada)
        return self.analise

    async def ler(self, sistema: str, jpeg: bytes, schema: dict[str, Any]) -> RespostaIA:
        self.leitura = None
        self.leitura = await self._cliente.ler(sistema, jpeg, schema)
        return self.leitura


@dataclass
class Medida:
    id: str
    caso: str
    tipo: str
    rotulo: str
    autor: str
    variacoes: dict[str, str]
    plano_b: str | None = None
    cer: float | None = None
    de_certo: bool | None = None
    acertos: dict[str, bool] = field(default_factory=dict)
    legivel_certo: bool = False
    motor_imagem: NivelRisco | None = None
    final_imagem: NivelRisco | None = None
    motor_texto: NivelRisco = "BAIXO"
    final_texto: NivelRisco = "BAIXO"
    injecao_pega: bool | None = None
    cita_app_sem_canal: bool | None = None
    ms_leitura: int = 0
    ms_analise: int = 0
    ms_total: int = 0
    tokens: Counter[str] = field(default_factory=Counter)


def _como_o_frontend(png: bytes) -> bytes:
    """O que o navegador faz antes de enviar: reduz às dimensões da Anthropic e reencoda em JPEG
    0,9 pelo canvas. Aqui, o mesmo com o Pillow."""
    with Image.open(io.BytesIO(png)) as aberta:
        rgb = aberta.convert("RGB")
    alvo = tamanho_alvo(*rgb.size)
    if alvo != rgb.size:
        rgb = rgb.resize(alvo, Image.Resampling.LANCZOS)
    saida = io.BytesIO()
    rgb.save(saida, "JPEG", quality=90)
    return saida.getvalue()


async def _conferir_camada(sdk: Any, modelo: str, png: bytes) -> str:
    jpeg = _como_o_frontend(png)
    with Image.open(io.BytesIO(jpeg)) as aberta:
        largura, altura = aberta.size
    try:
        contagem = await sdk.messages.count_tokens(
            model=modelo,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64.standard_b64encode(jpeg).decode("ascii"),
                            },
                            "transformations": {"oversized_image": "error"},
                        },
                        {"type": "text", "text": "Leia o print acima."},
                    ],
                }
            ],
        )
    except Exception as exc:
        return f"não confirmada ({type(exc).__name__}) para {largura}x{altura}"
    return (
        f"confirmada: {largura}x{altura} aceita sem redução (`oversized_image: error`), "
        f"{contagem.input_tokens} tokens de entrada na contagem"
    )


async def _medir(
    item: dict[str, Any],
    caso: Caso,
    png: bytes,
    leitor: LeitorDePrint,
    analisador: AnalisadorIA,
    contador: ClienteQueContaTudo,
    timeout_imagem: float,
    motivo: MotivoDoPlanoB,
) -> Medida:
    servico = obter_servico_analise()
    extrator = URLExtractor(carregar_regras().urls)
    esperadas = mensagens_esperadas(item, caso)
    texto_original = esperadas[-1][1]
    medida = Medida(
        id=item["id"],
        caso=item["caso"],
        tipo=item["tipo"],
        rotulo=item["rotulo"],
        autor=item["autor"],
        variacoes={
            chave: str(item[chave])
            for chave in ("layout", "remetente", "aviso", "primeira", "tema")
        },
    )
    gabarito = gabarito_do_contexto(item, bool(extrator.extrair(texto_original)))

    # Caminho do texto, para comparar: o mesmo caso, colado.
    resposta_texto = servico.analisar(texto_original)
    medida.motor_texto = resposta_texto.nivel_motor
    resultado_texto = await analisador.avaliar(
        EntradaIA(
            mensagem=texto_original,
            nivel_motor=resposta_texto.nivel_motor,
            fatores=tuple(resposta_texto.fatores),
            links=tuple(resposta_texto.links),
        )
    )
    medida.final_texto = combinar(
        resposta_texto.nivel_motor, resultado_texto.nivel_sugerido if resultado_texto else None
    )
    if contador.analise:
        medida.tokens["texto_entrada"] += contador.analise.tokens_entrada
        medida.tokens["texto_saida"] += contador.analise.tokens_saida

    # Caminho da imagem.
    inicio = time.perf_counter()
    preparada = preparar_imagem(_como_o_frontend(png), 5 * 1024 * 1024)
    try:
        leitura = await leitor.ler(preparada)
    except LeituraFalhou as falha:
        medida.ms_leitura = medida.ms_total = _ms(inicio)
        medida.plano_b = falha.motivo
        medida.legivel_certo = gabarito["legivel"] == "nao" and falha.motivo == "ilegivel"
        if contador.leitura:
            medida.tokens["leitura_entrada"] += contador.leitura.tokens_entrada
            medida.tokens["leitura_saida"] += contador.leitura.tokens_saida
        return medida
    medida.ms_leitura = _ms(inicio)
    medida.tokens["leitura_entrada"] += leitura.tokens_entrada
    medida.tokens["leitura_saida"] += leitura.tokens_saida
    medida.legivel_certo = gabarito["legivel"] == "sim"
    lido = "\n\n".join(m.texto for m in leitura.mensagens)
    medida.cer = taxa_de_erro_por_caractere(lido, texto_esperado_da_leitura(item, caso))
    medida.de_certo = [m.de for m in leitura.mensagens] == [de for de, _ in esperadas]
    contexto = leitura.contexto.model_dump()
    for campo in CAMPOS:
        esperado = gabarito[campo]
        medida.acertos[campo] = (
            contexto[campo] in esperado
            if isinstance(esperado, list)
            else contexto[campo] == esperado
        )

    recebido = texto_do_print(leitura.mensagens)
    if recebido.strip():
        antes_da_analise = time.perf_counter()
        resposta = servico.analisar(recebido)
        motivo.motivo = None
        resultado = await analisador.avaliar(
            EntradaIA(
                mensagem=recebido,
                nivel_motor=resposta.nivel_motor,
                fatores=tuple(resposta.fatores),
                links=tuple(resposta.links),
                print=PrintParaIA(mensagens=leitura.mensagens, contexto=leitura.contexto),
            ),
            timeout_s=timeout_imagem,
        )
        medida.ms_analise = _ms(antes_da_analise)
        medida.motor_imagem = resposta.nivel_motor
        medida.final_imagem = combinar(
            resposta.nivel_motor, resultado.nivel_sugerido if resultado else None
        )
        if resultado is None:
            medida.plano_b = f"análise: {motivo.motivo}"
        elif resultado.explicacao is not None and leitura.contexto.canal in (
            "outro",
            "nao_identificado",
        ):
            escrito = " ".join(
                [
                    resultado.explicacao.tipo,
                    *resultado.explicacao.sinais,
                    *resultado.explicacao.o_que_fazer,
                ]
            ).lower()
            medida.cita_app_sem_canal = any(app in escrito for app in APLICATIVOS)
        if contador.analise:
            medida.tokens["analise_entrada"] += contador.analise.tokens_entrada
            medida.tokens["analise_saida"] += contador.analise.tokens_saida
        if item["tipo"] == "injecao":
            categorias = {fator.categoria for fator in resposta.fatores}
            medida.injecao_pega = "instrucao_ao_analisador" in categorias
    medida.ms_total = _ms(inicio)
    return medida


def _ms(inicio: float) -> int:
    return round((time.perf_counter() - inicio) * 1000)


async def _rodar(divisao: str) -> tuple[list[Medida], str, str]:
    from anthropic import AsyncAnthropic

    from app.core.config import get_settings

    settings = get_settings()
    if settings.anthropic_api_key is None:
        raise SystemExit("Defina ANTHROPIC_API_KEY no .env da raiz do repositório.")
    if not LISTA.exists() or not PASTA_PRINTS.exists():
        raise SystemExit("Rode antes: uv run python -m tools.gerar_prints")
    lista = carregar_lista(divisao)
    if not lista:
        raise SystemExit(f"Sem prints de {divisao}: rode tools.gerar_prints --divisao {divisao}")
    casos = {caso.id: caso for caso in carregar_corpus(PASTA_CASOS)}
    sdk = AsyncAnthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
        timeout=settings.ia_timeout_s,
        max_retries=0,
    )
    contador = ClienteQueContaTudo(
        ClienteAnthropic(
            sdk,
            modelo=settings.ia_modelo,
            max_tokens=settings.ia_max_tokens,
            max_tokens_leitura=settings.ia_max_tokens_leitura,
        )
    )
    leitor = LeitorDePrint(contador, timeout_s=settings.ia_timeout_leitura_s)
    analisador = AnalisadorIA(contador, timeout_s=settings.ia_timeout_s)
    motivo = MotivoDoPlanoB()
    logging.getLogger("app.formulator.analisador").addHandler(motivo)
    medidas = []
    try:
        primeiro = (PASTA_PRINTS / f"{lista[0]['id']}.png").read_bytes()
        camada = await _conferir_camada(sdk, settings.ia_modelo, primeiro)
        print(f"Camada de resolução: {camada}")
        for numero, item in enumerate(lista, start=1):
            png = (PASTA_PRINTS / f"{item['id']}.png").read_bytes()
            medida = await _medir(
                item,
                casos[item["caso"]],
                png,
                leitor,
                analisador,
                contador,
                settings.ia_timeout_analise_imagem_s,
                motivo,
            )
            medidas.append(medida)
            print(
                f"  {numero}/{len(lista)} {item['id']}: {medida.ms_total} ms"
                + (f" (plano B: {medida.plano_b})" if medida.plano_b else "")
            )
    finally:
        await sdk.close()
    return medidas, settings.ia_modelo, camada


# ── Relatório ────────────────────────────────────────────────────────────────────────────────


def _pct(parte: int, todo: int) -> str:
    return f"{parte}/{todo} ({100 * parte / todo:.0f}%)" if todo else "—"


def _custo(tokens: Counter[str], prefixo: str) -> float:
    entrada = tokens[f"{prefixo}_entrada"]
    saida = tokens[f"{prefixo}_saida"]
    return (entrada * PRECO_ENTRADA + saida * PRECO_SAIDA) / 1_000_000


def montar_relatorio(
    medidas: list[Medida], modelo: str, camada: str, divisao: str = "calibracao"
) -> str:
    lidas = [m for m in medidas if m.cer is not None]
    normais = [m for m in lidas if m.tipo == "normal"]
    cers = sorted(m.cer for m in normais if m.cer is not None)
    tokens: Counter[str] = Counter()
    for medida in medidas:
        tokens.update(medida.tokens)
    imagem = [m for m in medidas if m.tipo != "ilegivel"]

    linhas = [
        f"# Avaliação dos prints sintéticos — {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"- **Modelo:** `{modelo}` · **camada de resolução:** {camada}",
        f"- **Commit:** {_commit()} · **hash do corpus:** `{hash_do_corpus(PASTA_CASOS)[:16]}` · "
        f"**semente dos prints:** {SEMENTE_PRINTS}",
        f"- **Prints:** {len(medidas)} ({Counter(m.tipo for m in medidas)}), todos da "
        f"divisão `{divisao}`, sintéticos (`tools/gerar_prints.py`). Autores dos casos: "
        f"{dict(Counter(m.autor for m in medidas))}.",
        "",
        "## Leitura",
        "",
    ]
    if cers:
        linhas.append(
            f"- **Taxa de erro por caractere (CER)**, {len(cers)} prints normais lidos: p50 "
            f"{percentil_f(cers, 0.5):.3f} · p95 {percentil_f(cers, 0.95):.3f} · máxima "
            f"{max(cers):.3f} · média {sum(cers) / len(cers):.3f}."
        )
        exatos = sum(1 for c in cers if c == 0)
        linhas.append(f"- Transcrição sem nenhum erro: {_pct(exatos, len(cers))}.")
    linhas.append(
        f"- **Quem mandou cada mensagem** certo em todas as mensagens do print: "
        f"{_pct(sum(1 for m in normais if m.de_certo), len(normais))}."
    )
    linhas += ["", "| Campo do contexto | Acerto |", "|---|---|"]
    for campo in CAMPOS:
        acertos = [m.acertos[campo] for m in normais if campo in m.acertos]
        linhas.append(f"| `{campo}` | {_pct(sum(acertos), len(acertos))} |")
    linhas += [
        "",
        "`canal` só tem resposta certa nos layouts de e-mail e SMS; no chat genérico vale "
        "`outro` ou `nao_identificado`, porque o desenho não imita aplicativo nenhum. A "
        "transcrição do caso 0035 (injeção) tem um caractere invisível que inverte o texto na "
        "tela: a leitura transcreve o que aparece, e a taxa de erro desse print conta isso.",
        "",
        "Por variação (CER médio; prints normais):",
        "",
        "| Variação | Valor | Prints | CER médio | `remetente_salvo` | `aviso_do_app` | "
        "`primeira_mensagem` |",
        "|---|---|---|---|---|---|---|",
    ]
    for chave in ("layout", "remetente", "aviso", "primeira", "tema"):
        for valor in sorted({m.variacoes[chave] for m in normais}):
            grupo = [m for m in normais if m.variacoes[chave] == valor]
            media = sum(m.cer or 0 for m in grupo) / len(grupo)
            celulas = [
                _pct(sum(m.acertos[c] for m in grupo), len(grupo))
                for c in ("remetente_salvo", "aviso_do_app", "primeira_mensagem")
            ]
            linhas.append(
                f"| {chave} | {valor} | {len(grupo)} | {media:.3f} | " + " | ".join(celulas) + " |"
            )

    ilegiveis = [m for m in medidas if m.tipo == "ilegivel"]
    falsos_ilegiveis = [
        m.id for m in medidas if m.tipo != "ilegivel" and m.plano_b and m.cer is None
    ]
    injecoes = [m for m in medidas if m.tipo == "injecao"]
    sem_canal = [m for m in medidas if m.cita_app_sem_canal is not None]
    cita = [m for m in sem_canal if m.cita_app_sem_canal]
    linhas += [
        "",
        "## Plano B e injeção",
        "",
        f"- **Borrados de propósito no plano B** (`ilegivel`): "
        f"{_pct(sum(1 for m in ilegiveis if m.legivel_certo), len(ilegiveis))} "
        f"({', '.join(f'{m.id}: {m.plano_b or "lido"}' for m in ilegiveis)}).",
        f"- **Prints legíveis que caíram no plano B da leitura:** "
        f"{', '.join(falsos_ilegiveis) or 'nenhum'}.",
        f"- **Injeção pega pelo motor** (`instrucao_ao_analisador`): "
        f"{_pct(sum(1 for m in injecoes if m.injecao_pega), len(injecoes))}; nível final "
        f"{', '.join(f'{m.id}: {m.final_imagem}' for m in injecoes) or '—'}.",
        "",
        "## Conselho",
        "",
        f"- **Explicação que cita um aplicativo pelo nome sem a leitura ter identificado o "
        f"canal** (`outro` ou `nao_identificado`): {_pct(len(cita), len(sem_canal))}"
        f"{' (' + ', '.join(m.id for m in cita) + ')' if cita else ''}.",
        "",
        "## Nível: imagem contra texto do mesmo caso",
        "",
    ]
    comparaveis = [m for m in imagem if m.motor_imagem is not None]
    total = len(comparaveis)
    motor_igual = sum(m.motor_imagem == m.motor_texto for m in comparaveis)
    final_igual = sum(m.final_imagem == m.final_texto for m in comparaveis)
    abaixo = [m for m in comparaveis if _posicao(m.final_imagem) < _ORDEM[m.final_texto]]
    acima = [m for m in comparaveis if _posicao(m.final_imagem) > _ORDEM[m.final_texto]]
    linhas += [
        f"- **Motor igual:** {_pct(motor_igual, total)} · **final igual:** "
        f"{_pct(final_igual, total)}.",
        f"- **Imagem abaixo do texto** (final): {_mudancas(abaixo)}.",
        f"- **Imagem acima do texto** (final): {_mudancas(acima)}.",
    ]
    for rotulo, titulo in (
        ("golpe", "Golpes em MÉDIO ou ALTO"),
        ("legitimo", "Legítimas em MÉDIO ou ALTO (alarme)"),
    ):
        grupo = [m for m in comparaveis if m.rotulo == rotulo and m.tipo == "normal"]
        na_imagem = sum(m.final_imagem != "BAIXO" for m in grupo)
        no_texto = sum(m.final_texto != "BAIXO" for m in grupo)
        linhas.append(
            f"- **{titulo}:** imagem {_pct(na_imagem, len(grupo))} · texto "
            f"{_pct(no_texto, len(grupo))}."
        )

    leituras = sorted(m.ms_leitura for m in medidas)
    analises = sorted(m.ms_analise for m in comparaveis)
    totais = sorted(m.ms_total for m in medidas)
    planos = Counter(m.plano_b for m in medidas if m.plano_b and m.plano_b.startswith("análise"))
    custo_imagem = _custo(tokens, "leitura") + _custo(tokens, "analise")
    linhas += [
        "",
        "## Tempo e custo",
        "",
        f"- **Leitura:** p50 {percentil(leituras, 0.5)} ms · p95 {percentil(leituras, 0.95)} ms · "
        f"máxima {max(leituras)} ms (teto 10 s).",
        f"- **Análise da IA no caminho de imagem:** p50 {percentil(analises, 0.5)} ms · p95 "
        f"{percentil(analises, 0.95)} ms · máxima {max(analises)} ms (teto 10 s).",
        f"- **Total do print** (validação + leitura + motor + IA, sem o registro): p50 "
        f"{percentil(totais, 0.5)} ms · p95 {percentil(totais, 0.95)} ms · máxima {max(totais)} ms "
        "(RNF02: < 30 s).",
        "- **Plano B da análise no caminho de imagem:** "
        + (", ".join(f"{k}: {n}" for k, n in sorted(planos.items())) or "nenhum")
        + ".",
        f"- **Tokens da leitura:** {tokens['leitura_entrada']} de entrada, "
        f"{tokens['leitura_saida']} de saída · **da análise (imagem):** "
        f"{tokens['analise_entrada']} / {tokens['analise_saida']} · **da análise (texto, "
        f"comparação):** {tokens['texto_entrada']} / {tokens['texto_saida']}.",
        f"- **Custo estimado por print** (leitura + análise): US$ "
        f"{custo_imagem / len(medidas):.5f}; **por texto:** US$ "
        f"{_custo(tokens, 'texto') / len(medidas):.5f} (preço de tabela em `tools/testar_ia.py`; "
        "estimativa, não fatura).",
        "",
        "## Por print",
        "",
        "| Print | Caso | Tipo | Rótulo | Layout | Remetente | Aviso | 1ª | Tema | CER | "
        "Contexto | Motor img/txt | Final img/txt | Leitura ms | Total ms | Plano B |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for m in medidas:
        contexto = f"{sum(m.acertos.values())}/{len(m.acertos)}" if m.acertos else "—"
        cer = f"{m.cer:.3f}" if m.cer is not None else "—"
        v = m.variacoes
        linhas.append(
            f"| {m.id} | {m.caso} | {m.tipo} | {m.rotulo} | {v['layout']} | {v['remetente']} | "
            f"{v['aviso']} | {v['primeira']} | {v['tema']} | {cer} | {contexto} | "
            f"{m.motor_imagem or '—'}/{m.motor_texto} | {m.final_imagem or '—'}/{m.final_texto} | "
            f"{m.ms_leitura} | {m.ms_total} | {m.plano_b or '—'} |"
        )
    return "\n".join(linhas)


def _posicao(nivel: NivelRisco | None) -> int:
    return _ORDEM[nivel] if nivel is not None else -1


def _mudancas(medidas: list[Medida]) -> str:
    return ", ".join(f"{m.id} ({m.final_texto}→{m.final_imagem})" for m in medidas) or "nenhum"


def percentil_f(valores: list[float], fracao: float) -> float:
    """Percentil pelo vizinho mais próximo, como o `percentil` do `avaliar_corpus`, para float."""
    ordenados = sorted(valores)
    indice = max(0, min(len(ordenados) - 1, round(fracao * len(ordenados) + 0.5) - 1))
    return ordenados[indice]


def _caminho_novo(divisao: str) -> Any:
    PASTA_RELATORIOS.mkdir(parents=True, exist_ok=True)
    sufixo_da_divisao = "-teste" if divisao == "teste" else ""
    base = f"{datetime.now():%Y-%m-%d}-prints{sufixo_da_divisao}"
    caminho = PASTA_RELATORIOS / f"{base}.md"
    sufixo = 2
    while caminho.exists():
        caminho = PASTA_RELATORIOS / f"{base}-{sufixo}.md"
        sufixo += 1
    return caminho


def main(argumentos: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--divisao", choices=("calibracao", "teste"), default="calibracao")
    divisao = parser.parse_args(argumentos).divisao
    medidas, modelo, camada = asyncio.run(_rodar(divisao))
    relatorio = montar_relatorio(medidas, modelo, camada, divisao)
    caminho = _caminho_novo(divisao)
    caminho.write_text(relatorio + "\n", encoding="utf-8", newline="\n")
    print(f"Relatório: {caminho.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
