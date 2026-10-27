"""Mede o motor de risco (e, se pedido, motor + IA) contra o corpus rotulado (ADR-0005, ADR-0021).

    cd backend
    uv run python -m tools.avaliar_corpus                              # motor, todas as divisões
    uv run python -m tools.avaliar_corpus --com-ia --divisao teste     # motor + IA real
    uv run python -m tools.avaliar_corpus --gravar-linha-de-base       # regrava o gate do CI

O modo `--motor` (padrão) é offline e determinístico: o mesmo corpus e o mesmo `regras.yaml` dão
sempre o mesmo número. O `--com-ia` chama a API da Anthropic com a chave do `.env` da raiz (pelo
mesmo `Settings` da aplicação, sem imprimi-la), em série, como em produção; não roda no CI.

Cada rodada escreve um relatório novo em `docs/avaliacoes/` (nunca sobrescreve) com o carimbo do
que foi medido: versão e cortes das regras, modelo, commit, hash do corpus e semente da divisão.
Erros aparecem só pelo id do caso — nem a mensagem nem a saída da IA vão para o relatório.

Regra que sustenta o número do teste: ajuste de peso, padrão ou prompt olha só a calibração.
"""

import argparse
import asyncio
import hashlib
import json
import logging
import math
import re
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml

from app.analyzers.normalizacao import normalizar
from app.analyzers.urls import URLExtractor
from app.api.deps import obter_servico_analise
from app.schemas.analise import NivelRisco
from app.scoring.combinacao import combinar
from app.scoring.regras import carregar_regras
from tools.sortear_divisao import PASTA_CASOS, SEMENTE

RAIZ = Path(__file__).resolve().parents[2]
PASTA_RELATORIOS = RAIZ / "docs" / "avaliacoes"
LINHA_DE_BASE = Path(__file__).parent / "linha_de_base_motor.json"

Rotulo = Literal["golpe", "legitimo"]

# Quantil 97,5% da normal padrão: o z do intervalo de 95%.
Z_95 = 1.959964

# §1.6 do RFC pela errata 14: precisão E recall acima disto, com MÉDIO = golpe.
LIMIAR_KPI = 0.85

# §1.6 e RNF02: tempo por consulta.
TETO_DE_TEMPO_MS = 30_000

# O gate do CI tolera um caso a mais de erro em cada proporção, nunca dois. Em casos, e não em
# pontos percentuais, porque o mesmo "3 p.p." vale dois golpes e só um legítimo na calibração.
MARGEM_EM_CASOS = 1

PROPORCOES_DO_GATE = (
    "golpes_medio_ou_mais",
    "golpes_alto",
    "alarme_medio_ou_mais",
    "alarme_alto",
)


# ── Corpus ───────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Caso:
    id: str
    conteudo: str
    rotulo: Rotulo
    autor: str
    divisao: str


@dataclass(frozen=True)
class Resultado:
    """O que o relatório recebe de cada caso. Sem o texto, de propósito: o que não está aqui não
    tem como vazar para o relatório."""

    id: str
    rotulo: Rotulo
    autor: str
    divisao: str
    nivel: NivelRisco


def carregar_corpus(pasta: Path) -> list[Caso]:
    casos = []
    for arquivo in sorted(pasta.glob("*.yaml")):
        with arquivo.open(encoding="utf-8") as aberto:
            dado = yaml.safe_load(aberto)
        casos.append(
            Caso(
                id=dado["id"],
                conteudo=dado["conteudo"],
                rotulo=dado["rotulo"],
                autor=dado["autor"],
                divisao=dado["divisao"],
            )
        )
    return casos


def hash_do_corpus(pasta: Path) -> str:
    """SHA-256 de nome e conteúdo de cada caso, em ordem. O fim de linha é normalizado porque o
    git no Windows pode trocar LF por CRLF no checkout, e o mesmo corpus teria dois hashes."""
    soma = hashlib.sha256()
    for arquivo in sorted(pasta.glob("*.yaml")):
        texto = arquivo.read_bytes().replace(b"\r\n", b"\n")
        soma.update(arquivo.name.encode() + b"\0" + texto + b"\0")
    return soma.hexdigest()


def avaliar(casos: list[Caso], classificar: Callable[[str], NivelRisco]) -> list[Resultado]:
    return [
        Resultado(
            id=caso.id,
            rotulo=caso.rotulo,
            autor=caso.autor,
            divisao=caso.divisao,
            nivel=classificar(caso.conteudo),
        )
        for caso in casos
    ]


_PIX = re.compile(r"\bpix\b")


def classificar_trivial(texto: str, extrator: URLExtractor) -> NivelRisco:
    """Linha de base trivial do ADR-0005: "tem link e a palavra PIX → golpe". Se o motor não
    bater isto com folga, as heurísticas não estão pagando o que custam."""
    tem_link = bool(extrator.extrair(texto))
    return "ALTO" if tem_link and _PIX.search(normalizar(texto)) else "BAIXO"


# ── Estatística ──────────────────────────────────────────────────────────────────────────────


def wilson(sucessos: int, total: int) -> tuple[float, float]:
    """Intervalo de 95% de Wilson. Ao contrário do intervalo normal, não colapsa em [0, 0] nem
    [1, 1] nos extremos — com 46 casos, 0 erros não é "certeza de zero"."""
    if total <= 0:
        raise ValueError("intervalo sem casos")
    p = sucessos / total
    z2 = Z_95**2
    denominador = 1 + z2 / total
    centro = (p + z2 / (2 * total)) / denominador
    margem = Z_95 * math.sqrt(p * (1 - p) / total + z2 / (4 * total**2)) / denominador
    return max(0.0, centro - margem), min(1.0, centro + margem)


def _pct(valor: float) -> str:
    return f"{valor * 100:.1f}".replace(".", ",") + "%"


@dataclass(frozen=True)
class Proporcao:
    sucessos: int
    total: int

    @property
    def valor(self) -> float | None:
        return self.sucessos / self.total if self.total else None

    @property
    def intervalo(self) -> tuple[float, float] | None:
        return wilson(self.sucessos, self.total) if self.total else None

    def formatar(self) -> str:
        if self.valor is None or self.intervalo is None:
            return f"{self.sucessos}/{self.total} (sem casos)"
        baixo, alto = self.intervalo
        return (
            f"{self.sucessos}/{self.total} = {_pct(self.valor)} "
            f"(IC 95%: {_pct(baixo)} a {_pct(alto)})"
        )


def percentil(valores: list[int], fracao: float) -> int:
    """Por posição (nearest-rank): o menor valor com pelo menos `fracao` dos casos até ele."""
    ordenados = sorted(valores)
    return ordenados[max(0, math.ceil(fracao * len(ordenados)) - 1)]


# ── Métricas ─────────────────────────────────────────────────────────────────────────────────

NIVEIS: tuple[NivelRisco, ...] = ("BAIXO", "MEDIO", "ALTO")


def matriz(resultados: list[Resultado]) -> dict[NivelRisco, dict[str, int]]:
    contagem: dict[NivelRisco, dict[str, int]] = {
        nivel: {"golpe": 0, "legitimo": 0} for nivel in NIVEIS
    }
    for resultado in resultados:
        contagem[resultado.nivel][resultado.rotulo] += 1
    return contagem


def _f1(precisao: Proporcao, recall: Proporcao) -> float | None:
    if precisao.valor is None or recall.valor is None or precisao.valor + recall.valor == 0:
        return None
    return 2 * precisao.valor * recall.valor / (precisao.valor + recall.valor)


@dataclass(frozen=True)
class Metricas:
    golpes_medio_ou_mais: Proporcao
    golpes_alto: Proporcao
    alarme_medio_ou_mais: Proporcao
    alarme_alto: Proporcao
    # Principal (ADR-0005): MÉDIO conta como golpe.
    precisao: Proporcao
    recall: Proporcao
    acuracia: Proporcao
    f1: float | None
    # Variante: MÉDIO conta como legítimo.
    precisao_so_alto: Proporcao
    recall_so_alto: Proporcao
    acuracia_so_alto: Proporcao
    f1_so_alto: float | None

    @property
    def kpi_atendido(self) -> bool:
        p, r = self.precisao.valor, self.recall.valor
        return p is not None and r is not None and p > LIMIAR_KPI and r > LIMIAR_KPI


def calcular_metricas(resultados: list[Resultado]) -> Metricas:
    m = matriz(resultados)
    golpes = sum(m[nivel]["golpe"] for nivel in NIVEIS)
    legitimas = sum(m[nivel]["legitimo"] for nivel in NIVEIS)
    total = golpes + legitimas

    vp = m["MEDIO"]["golpe"] + m["ALTO"]["golpe"]
    fp = m["MEDIO"]["legitimo"] + m["ALTO"]["legitimo"]
    vp_alto = m["ALTO"]["golpe"]
    fp_alto = m["ALTO"]["legitimo"]

    precisao = Proporcao(vp, vp + fp)
    recall = Proporcao(vp, golpes)
    precisao_so_alto = Proporcao(vp_alto, vp_alto + fp_alto)
    recall_so_alto = Proporcao(vp_alto, golpes)
    return Metricas(
        golpes_medio_ou_mais=recall,
        golpes_alto=recall_so_alto,
        alarme_medio_ou_mais=Proporcao(fp, legitimas),
        alarme_alto=Proporcao(fp_alto, legitimas),
        precisao=precisao,
        recall=recall,
        acuracia=Proporcao(vp + legitimas - fp, total),
        f1=_f1(precisao, recall),
        precisao_so_alto=precisao_so_alto,
        recall_so_alto=recall_so_alto,
        acuracia_so_alto=Proporcao(vp_alto + legitimas - fp_alto, total),
        f1_so_alto=_f1(precisao_so_alto, recall_so_alto),
    )


# ── Gate do CI ───────────────────────────────────────────────────────────────────────────────


def linha_de_base(
    resultados: list[Resultado], hash_corpus: str, versao_regras: int
) -> dict[str, Any]:
    m = calcular_metricas(resultados)
    base: dict[str, Any] = {
        "divisao": "calibracao",
        "versao_regras": versao_regras,
        "hash_corpus": hash_corpus,
        "semente": SEMENTE,
    }
    for nome in PROPORCOES_DO_GATE:
        proporcao: Proporcao = getattr(m, nome)
        base[nome] = {"sucessos": proporcao.sucessos, "total": proporcao.total}
    return base


def comparar_com_linha_de_base(atual: dict[str, Any], base: dict[str, Any]) -> list[str]:
    """Lista o que piorou além da margem. Vazia = passou. Melhorar nunca falha."""
    if atual["hash_corpus"] != base["hash_corpus"]:
        return [
            "o corpus mudou desde a linha de base: rode `python -m tools.avaliar_corpus "
            "--gravar-linha-de-base` e anote o antes e o depois no docs/diario.md"
        ]
    falhas = []
    for nome in PROPORCOES_DO_GATE:
        antes, agora = base[nome]["sucessos"], atual[nome]["sucessos"]
        # Nos golpes, subir é bom; no alarme falso, descer é bom.
        piora = antes - agora if nome.startswith("golpes") else agora - antes
        if piora > MARGEM_EM_CASOS:
            falhas.append(
                f"{nome}: {antes} → {agora} de {base[nome]['total']} "
                f"(piorou {piora} casos; a margem é {MARGEM_EM_CASOS})"
            )
    return falhas


# ── Relatório ────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Carimbo:
    quando: str
    modo: str
    versao_regras: int
    baixo_ate: int
    medio_ate: int
    modelo_ia: str
    commit: str
    hash_corpus: str
    semente: int


@dataclass(frozen=True)
class Avaliacao:
    """Uma coluna do relatório: quem classificou (motor, motor + IA, baseline) e o que deu."""

    nome: str
    resultados: list[Resultado]
    listar_erros: bool = False


_NOME_DIVISAO = {"calibracao": "calibração", "teste": "teste"}


def _recortes(resultados: list[Resultado]) -> list[tuple[str, set[str], bool]]:
    """(título, ids do recorte, lista erros?). Erros só por divisão, para não repetir ids."""
    recortes = []
    divisoes = [d for d in ("calibracao", "teste") if any(r.divisao == d for r in resultados)]
    for divisao in divisoes:
        ids = {r.id for r in resultados if r.divisao == divisao}
        recortes.append((_NOME_DIVISAO[divisao], ids, True))
    if len(divisoes) > 1:
        recortes.append(("total", {r.id for r in resultados}, False))
    for autor in sorted({r.autor for r in resultados}):
        ids = {r.id for r in resultados if r.autor == autor}
        recortes.append((f"autor {autor}", ids, False))
    return recortes


def _f1_texto(valor: float | None) -> str:
    return "—" if valor is None else f"{valor:.3f}".replace(".", ",")


def _kpi_texto(m: Metricas) -> str:
    veredito = "atende" if m.kpi_atendido else "não atende"
    p = "—" if m.precisao.valor is None else _pct(m.precisao.valor)
    r = "—" if m.recall.valor is None else _pct(m.recall.valor)
    return f"**{veredito}** (P {p}, R {r})"


def _linhas_de_metricas(nomes: list[str], metricas: list[Metricas]) -> list[str]:
    linhas = [
        "| Métrica | " + " | ".join(nomes) + " |",
        "|---|" + "---|" * len(nomes),
    ]
    campos: list[tuple[str, Callable[[Metricas], str]]] = [
        ("Golpes detectados (≥ MÉDIO)", lambda m: m.golpes_medio_ou_mais.formatar()),
        ("Golpes em ALTO", lambda m: m.golpes_alto.formatar()),
        ("Alarme falso: legítimas ≥ MÉDIO", lambda m: m.alarme_medio_ou_mais.formatar()),
        ("Alarme falso: legítimas em ALTO", lambda m: m.alarme_alto.formatar()),
        ("Precisão (MÉDIO = golpe)", lambda m: m.precisao.formatar()),
        ("Recall (MÉDIO = golpe)", lambda m: m.recall.formatar()),
        ("F1 (MÉDIO = golpe)", lambda m: _f1_texto(m.f1)),
        ("Acurácia (MÉDIO = golpe)", lambda m: m.acuracia.formatar()),
        ("Precisão (MÉDIO = legítimo)", lambda m: m.precisao_so_alto.formatar()),
        ("Recall (MÉDIO = legítimo)", lambda m: m.recall_so_alto.formatar()),
        ("F1 (MÉDIO = legítimo)", lambda m: _f1_texto(m.f1_so_alto)),
        ("Acurácia (MÉDIO = legítimo)", lambda m: m.acuracia_so_alto.formatar()),
        ("KPI §1.6 + errata 14 (P e R > 85%)", _kpi_texto),
    ]
    for titulo, extrair in campos:
        linhas.append(f"| {titulo} | " + " | ".join(extrair(m) for m in metricas) + " |")
    return linhas


def _ids(resultados: list[Resultado], rotulo: str, nivel: str) -> str:
    ids = sorted(r.id for r in resultados if r.rotulo == rotulo and r.nivel == nivel)
    return ", ".join(ids) if ids else "nenhum"


def montar_relatorio(
    carimbo: Carimbo, avaliacoes: list[Avaliacao], secao_ia: list[str] | None = None
) -> str:
    referencia = avaliacoes[0].resultados
    linhas = [
        f"# Avaliação do corpus — {carimbo.modo} ({carimbo.quando})",
        "",
        "| Carimbo | |",
        "|---|---|",
        f"| Quando | {carimbo.quando} |",
        f"| Modo | {carimbo.modo} |",
        f"| Regras | `regras.yaml` v{carimbo.versao_regras} · BAIXO ≤ {carimbo.baixo_ate} · "
        f"MÉDIO ≤ {carimbo.medio_ate} · ALTO {carimbo.medio_ate + 1}+ |",
        f"| Modelo da IA | {carimbo.modelo_ia} |",
        f"| Commit | {carimbo.commit} |",
        f"| Corpus | {len(referencia)} casos avaliados · SHA-256 `{carimbo.hash_corpus}` |",
        f"| Semente da divisão | {carimbo.semente} |",
        "",
        "- Corpus **sintético**: o número tende a ser otimista em relação a mensagens reais, e "
        'o "casos reais" do §1.6 do RFC não é atestado por ele (ADR-0021).',
        "- KPI pelo §1.6 do RFC com a errata 14: atende só com precisão **e** recall acima de "
        "85%, contando MÉDIO como golpe (ADR-0005). Intervalos: Wilson, 95%.",
        "- Erros aparecem só pelo id do caso. Os do **teste** estão aqui para relatar: ajuste "
        "de peso, padrão ou prompt olha só a calibração.",
        "",
    ]
    if secao_ia:
        linhas += [*secao_ia, ""]

    for titulo, ids, com_erros in _recortes(referencia):
        recorte = [[r for r in a.resultados if r.id in ids] for a in avaliacoes]
        golpes = sum(1 for r in recorte[0] if r.rotulo == "golpe")
        linhas += [
            f"## Recorte: {titulo} ({len(ids)} casos: {golpes} golpes, "
            f"{len(ids) - golpes} legítimas)",
            "",
            *_linhas_de_metricas(
                [a.nome for a in avaliacoes], [calcular_metricas(rs) for rs in recorte]
            ),
            "",
        ]
        for avaliacao, resultados in zip(avaliacoes, recorte, strict=True):
            if not avaliacao.listar_erros:
                continue
            m = matriz(resultados)
            linhas += [
                f"**Matriz — {avaliacao.nome}**",
                "",
                "| Nível | golpe | legítimo |",
                "|---|---|---|",
                *(f"| {n} | {m[n]['golpe']} | {m[n]['legitimo']} |" for n in NIVEIS),
                "",
            ]
            if com_erros:
                linhas += [
                    f"**Erros — {avaliacao.nome}**",
                    "",
                    f"- Golpe em BAIXO: {_ids(resultados, 'golpe', 'BAIXO')}",
                    f"- Legítima em ALTO: {_ids(resultados, 'legitimo', 'ALTO')}",
                    "",
                ]
    if not any(r.autor == "walter" for r in referencia):
        linhas += ["Casos do Walter: nenhum ainda no corpus (ADR-0021, viés de autoria).", ""]
    return "\n".join(linhas)


def _commit() -> str:
    try:
        curto = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=RAIZ,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
        sujo = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=RAIZ,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "desconhecido (git indisponível)"
    return f"`{curto}` com alterações locais" if sujo else f"`{curto}`"


def _caminho_novo(modo: str) -> Path:
    PASTA_RELATORIOS.mkdir(parents=True, exist_ok=True)
    base = f"{datetime.now():%Y-%m-%d}-{modo}"
    caminho = PASTA_RELATORIOS / f"{base}.md"
    sufixo = 2
    while caminho.exists():
        caminho = PASTA_RELATORIOS / f"{base}-{sufixo}.md"
        sufixo += 1
    return caminho


def _carimbo(modo: str, modelo_ia: str) -> Carimbo:
    regras = carregar_regras()
    return Carimbo(
        quando=f"{datetime.now():%Y-%m-%d %H:%M}",
        modo=modo,
        versao_regras=regras.versao,
        baixo_ate=regras.faixas.baixo_ate,
        medio_ate=regras.faixas.medio_ate,
        modelo_ia=modelo_ia,
        commit=_commit(),
        hash_corpus=hash_do_corpus(PASTA_CASOS),
        semente=SEMENTE,
    )


# ── Modo com IA ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Execucao:
    id: str
    rotulo: Rotulo
    nivel_motor: NivelRisco
    nivel_ia: NivelRisco | None
    final: NivelRisco
    latencia_ms: int
    plano_b: str | None  # "total: <motivo>", "explicação: <motivo>" ou None
    tokens_entrada: int
    tokens_saida: int


async def _rodar_com_ia(casos: list[Caso]) -> tuple[list[Execucao], str]:
    # Importados aqui para o modo motor (e o CI) não dependerem do SDK nem da chave.
    from anthropic import AsyncAnthropic

    from app.core.config import get_settings
    from app.formulator.analisador import AnalisadorIA
    from app.formulator.cliente import ClienteAnthropic
    from app.formulator.prompt import EntradaIA
    from tools.testar_ia import ClienteQueConta, MotivoDoPlanoB

    settings = get_settings()
    if settings.anthropic_api_key is None:
        raise SystemExit("Defina ANTHROPIC_API_KEY no .env da raiz do repositório.")
    sdk = AsyncAnthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
        timeout=settings.ia_timeout_s,
        max_retries=0,
    )
    cliente = ClienteQueConta(
        ClienteAnthropic(sdk, modelo=settings.ia_modelo, max_tokens=settings.ia_max_tokens)
    )
    analisador = AnalisadorIA(cliente, timeout_s=settings.ia_timeout_s)
    motivo = MotivoDoPlanoB()
    logging.getLogger("app.formulator.analisador").addHandler(motivo)
    servico = obter_servico_analise()

    execucoes = []
    try:
        for numero, caso in enumerate(casos, start=1):
            motivo.motivo = None
            inicio = time.perf_counter()
            resposta = servico.analisar(caso.conteudo)
            resultado = await analisador.avaliar(
                EntradaIA(
                    mensagem=caso.conteudo,
                    nivel_motor=resposta.nivel_motor,
                    fatores=tuple(resposta.fatores),
                    urls=tuple(resposta.urls_analisadas),
                )
            )
            latencia_ms = round((time.perf_counter() - inicio) * 1000)
            nivel_ia = resultado.nivel_sugerido if resultado else None
            if resultado is None:
                plano_b: str | None = f"total: {motivo.motivo}"
            elif resultado.explicacao is None:
                plano_b = f"explicação: {motivo.motivo}"
            else:
                plano_b = None
            ultima = cliente.ultima
            execucoes.append(
                Execucao(
                    id=caso.id,
                    rotulo=caso.rotulo,
                    nivel_motor=resposta.nivel_motor,
                    nivel_ia=nivel_ia,
                    final=combinar(resposta.nivel_motor, nivel_ia),
                    latencia_ms=latencia_ms,
                    plano_b=plano_b,
                    tokens_entrada=ultima.tokens_entrada if ultima else 0,
                    tokens_saida=ultima.tokens_saida if ultima else 0,
                )
            )
            print(f"  {numero}/{len(casos)} {caso.id}: {latencia_ms} ms")
    finally:
        await sdk.close()
    return execucoes, settings.ia_modelo


_ORDEM = {nivel: posicao for posicao, nivel in enumerate(NIVEIS)}


def secao_da_ia(execucoes: list[Execucao]) -> list[str]:
    from tools.testar_ia import PRECO_ENTRADA, PRECO_SAIDA

    latencias = [e.latencia_ms for e in execucoes]
    entrada = sum(e.tokens_entrada for e in execucoes)
    saida = sum(e.tokens_saida for e in execucoes)
    custo = (entrada * PRECO_ENTRADA + saida * PRECO_SAIDA) / 1_000_000
    maxima = max(latencias)
    planos = Counter(e.plano_b for e in execucoes if e.plano_b)
    subiu = [e for e in execucoes if e.final != e.nivel_motor]
    abaixo = [e for e in execucoes if e.nivel_ia and _ORDEM[e.nivel_ia] < _ORDEM[e.nivel_motor]]
    subiu_legitima = sorted(e.id for e in subiu if e.rotulo == "legitimo")
    subiu_golpe = sorted(e.id for e in subiu if e.rotulo == "golpe")
    dentro = "dentro" if maxima < TETO_DE_TEMPO_MS else "**fora**"
    return [
        "## Só no modo com IA",
        "",
        f"- **Latência por análise** (motor + IA, chamadas em série): p50 "
        f"{percentil(latencias, 0.5)} ms · p95 {percentil(latencias, 0.95)} ms · máxima "
        f"{maxima} ms — {dentro} do teto de 30 s (§1.6 e RNF02). Mede só texto: OCR e "
        "reputação ainda não existem.",
        f"- **Tokens:** {entrada} de entrada, {saida} de saída · **custo estimado** "
        f"US$ {custo:.4f} (preço de tabela em `tools/testar_ia.py`; estimativa, não fatura).",
        "- **Plano B:** "
        + (", ".join(f"{motivo}: {n}" for motivo, n in sorted(planos.items())) or "nenhum")
        + f" (de {len(execucoes)} análises).",
        f"- **A IA subiu o nível** em {len(subiu)} casos: golpes {', '.join(subiu_golpe) or '—'}"
        f"; legítimas {', '.join(subiu_legitima) or '—'}.",
        f"- **A IA sugeriu abaixo do motor** em {len(abaixo)} casos (a regra fixa manteve o "
        "do motor).",
    ]


# ── CLI ──────────────────────────────────────────────────────────────────────────────────────


def _gravar_linha_de_base(casos: list[Caso]) -> int:
    servico = obter_servico_analise()
    calibracao = [caso for caso in casos if caso.divisao == "calibracao"]
    resultados = avaliar(calibracao, lambda texto: servico.analisar(texto).nivel_motor)
    nova = linha_de_base(resultados, hash_do_corpus(PASTA_CASOS), carregar_regras().versao)
    antiga = (
        json.loads(LINHA_DE_BASE.read_text(encoding="utf-8")) if LINHA_DE_BASE.exists() else None
    )
    LINHA_DE_BASE.write_text(
        json.dumps(nova, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Linha de base gravada em {LINHA_DE_BASE.relative_to(RAIZ)} (calibração).")
    for nome in PROPORCOES_DO_GATE:
        antes = f"{antiga[nome]['sucessos']}/{antiga[nome]['total']}" if antiga else "—"
        print(f"  {nome}: {antes} → {nova[nome]['sucessos']}/{nova[nome]['total']}")
    return 0


def main(argumentos: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--motor", action="store_true", help="só o motor, offline (padrão)")
    modo.add_argument("--com-ia", action="store_true", help="motor + IA real; custa centavos")
    modo.add_argument(
        "--gravar-linha-de-base", action="store_true", help="regrava o gate do CI (calibração)"
    )
    parser.add_argument("--divisao", choices=("calibracao", "teste", "todas"))
    args = parser.parse_args(argumentos)

    casos = carregar_corpus(PASTA_CASOS)
    if args.gravar_linha_de_base:
        return _gravar_linha_de_base(casos)
    if args.com_ia and args.divisao is None:
        parser.error("--com-ia exige --divisao (calibracao, teste ou todas)")
    divisao = args.divisao or "todas"
    if divisao != "todas":
        casos = [caso for caso in casos if caso.divisao == divisao]

    servico = obter_servico_analise()
    extrator = URLExtractor(carregar_regras().urls)
    motor = avaliar(casos, lambda texto: servico.analisar(texto).nivel_motor)
    trivial = avaliar(casos, lambda texto: classificar_trivial(texto, extrator))

    if args.com_ia:
        execucoes, modelo = asyncio.run(_rodar_com_ia(casos))
        final_por_id = {e.id: e.final for e in execucoes}
        final = [Resultado(r.id, r.rotulo, r.autor, r.divisao, final_por_id[r.id]) for r in motor]
        carimbo = _carimbo(f"com-ia ({divisao})", modelo)
        avaliacoes = [
            Avaliacao("Motor + IA (final)", final, listar_erros=True),
            Avaliacao("Só o motor", motor, listar_erros=True),
            Avaliacao("Linha de base trivial", trivial),
        ]
        relatorio = montar_relatorio(carimbo, avaliacoes, secao_da_ia(execucoes))
        caminho = _caminho_novo("com-ia")
    else:
        carimbo = _carimbo(f"motor ({divisao})", "não usado")
        avaliacoes = [
            Avaliacao("Motor", motor, listar_erros=True),
            Avaliacao("Linha de base trivial", trivial),
        ]
        relatorio = montar_relatorio(carimbo, avaliacoes)
        caminho = _caminho_novo("motor")

    caminho.write_text(relatorio + "\n", encoding="utf-8", newline="\n")
    print(f"Relatório: {caminho.relative_to(RAIZ)}")
    principal = avaliacoes[0]
    for titulo, ids, _ in _recortes(principal.resultados):
        m = calcular_metricas([r for r in principal.resultados if r.id in ids])
        print(f"  {titulo}: {_kpi_texto(m).replace('**', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
