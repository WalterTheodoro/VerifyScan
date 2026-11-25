"""Reputação de links (ADR-0028): Google Safe Browsing e VirusTotal, só pelo domínio.

Nenhum teste sai para a rede: o transporte HTTP é o `httpx.MockTransport`, que entrega cada
requisição a uma função daqui. É ela que anota o que sairia do processo, e é por essas anotações
que os testes de privacidade conferem que só o domínio foi enviado.
"""

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from pydantic import ValidationError

from app.api.conta import _fatores_do_historico
from app.api.deps import obter_servico_analise, obter_verificador_de_reputacao
from app.core.logs import configurar_logs
from app.core.metricas import REGISTRO, exposicao
from app.core.sentry import limpar_evento
from app.reputation.fatores import fatores_de_reputacao
from app.reputation.safe_browsing import ClienteSafeBrowsing
from app.reputation.tipos import Alvo, Apontamento, FonteIndisponivel
from app.reputation.verificador import VerificadorDeReputacao, chave_de_cache
from app.reputation.virustotal import ClienteVirusTotal
from app.scoring.regras import carregar_regras
from app.services.repositorio_historico import FatorDoHistorico
from tests.conftest import RelogioFalso, RepositorioReputacaoEmMemoria, settings_de_teste

CHAVE_GOOGLE = "CHAVE-SECRETA-DO-GOOGLE"
CHAVE_VT = "CHAVE-SECRETA-DO-VIRUSTOTAL"
LIMIARES = carregar_regras().reputacao.virustotal

Manipulador = Callable[[httpx.Request], httpx.Response]


class Bases:
    """As duas bases de mentira. Anota toda requisição e responde o que o teste mandar."""

    def __init__(self) -> None:
        self.requisicoes: list[httpx.Request] = []
        # host → segundos de validade (`cacheDuration`) do aviso do Google.
        self.google_aponta: dict[str, int] = {}
        # domínio → (malicious, suspicious) no VirusTotal. Fora daqui: 404, desconhecido.
        self.virustotal: dict[str, tuple[int, int]] = {}
        self.google_responde: Manipulador | None = None
        self.virustotal_responde: Manipulador | None = None

    def __call__(self, requisicao: httpx.Request) -> httpx.Response:
        self.requisicoes.append(requisicao)
        if requisicao.url.host == "safebrowsing.googleapis.com":
            if self.google_responde is not None:
                return self.google_responde(requisicao)
            consultadas = [
                item["url"]
                for item in json.loads(requisicao.content)["threatInfo"]["threatEntries"]
            ]
            achados = [
                {
                    "threatType": "SOCIAL_ENGINEERING",
                    "platformType": "ANY_PLATFORM",
                    "threatEntryType": "URL",
                    "threat": {"url": url},
                    "cacheDuration": f"{self.google_aponta[httpx.URL(url).host]}.000s",
                }
                for url in consultadas
                if httpx.URL(url).host in self.google_aponta
            ]
            return httpx.Response(200, json={"matches": achados} if achados else {})
        if self.virustotal_responde is not None:
            return self.virustotal_responde(requisicao)
        dominio = requisicao.url.path.rsplit("/", 1)[-1]
        if dominio not in self.virustotal:
            return httpx.Response(404, json={"error": {"code": "NotFoundError"}})
        maliciosos, suspeitos = self.virustotal[dominio]
        estatisticas = {"malicious": maliciosos, "suspicious": suspeitos, "harmless": 60}
        return httpx.Response(
            200, json={"data": {"attributes": {"last_analysis_stats": estatisticas}}}
        )

    def do_google(self) -> list[httpx.Request]:
        return [r for r in self.requisicoes if r.url.host == "safebrowsing.googleapis.com"]

    def do_virustotal(self) -> list[httpx.Request]:
        return [r for r in self.requisicoes if r.url.host == "www.virustotal.com"]

    def tudo_que_saiu(self) -> str:
        """Endereço, cabeçalhos e corpo de toda requisição, num texto só."""
        return "\n".join(
            f"{r.method} {r.url} {dict(r.headers)} {r.content.decode()}" for r in self.requisicoes
        )


@pytest.fixture
def bases() -> Bases:
    return Bases()


@pytest.fixture
async def http(bases: Bases) -> Any:
    async with httpx.AsyncClient(transport=httpx.MockTransport(bases)) as cliente:
        yield cliente


def _verificador(
    http: httpx.AsyncClient,
    repositorio: RepositorioReputacaoEmMemoria,
    relogio: RelogioFalso,
    *,
    google: bool = True,
    virustotal: bool = True,
    timeout_s: float = 3,
    por_minuto: int = 4,
    por_dia: int = 500,
) -> VerificadorDeReputacao:
    return VerificadorDeReputacao(
        safe_browsing=ClienteSafeBrowsing(http, CHAVE_GOOGLE, timeout_s) if google else None,
        virustotal=ClienteVirusTotal(http, CHAVE_VT, timeout_s, LIMIARES) if virustotal else None,
        repositorio=repositorio,
        agora=relogio,
        timeout_s=timeout_s,
        virustotal_por_minuto=por_minuto,
        virustotal_por_dia=por_dia,
    )


@pytest.fixture
def verificador(
    http: httpx.AsyncClient,
    reputacao_em_memoria: RepositorioReputacaoEmMemoria,
    relogio: RelogioFalso,
) -> VerificadorDeReputacao:
    return _verificador(http, reputacao_em_memoria, relogio)


GOLPE = Alvo(host="entrar.golpe-exemplo.example", dominio="golpe-exemplo.example")
OUTRO = Alvo(host="outro-exemplo.example", dominio="outro-exemplo.example")


async def _verificar_e_guardar(
    verificador: VerificadorDeReputacao, alvos: list[Alvo]
) -> tuple[list[Apontamento], bool]:
    resultado = await verificador.verificar(alvos)
    await verificador.guardar(resultado.a_guardar, timeout_s=2)
    return list(resultado.apontamentos), resultado.indisponivel


# ── Google Safe Browsing ─────────────────────────────────────────────────────────────────────


async def test_google_aponta_o_host_e_devolve_a_validade(
    bases: Bases, http: httpx.AsyncClient
) -> None:
    bases.google_aponta = {GOLPE.host: 300}

    apontados = await ClienteSafeBrowsing(http, CHAVE_GOOGLE, 3).consultar([GOLPE.host, OUTRO.host])

    assert apontados == {GOLPE.host: 300.0}


async def test_google_sem_correspondencia_devolve_vazio(http: httpx.AsyncClient) -> None:
    assert await ClienteSafeBrowsing(http, CHAVE_GOOGLE, 3).consultar([OUTRO.host]) == {}


async def test_google_recebe_so_http_e_https_do_host(bases: Bases, http: httpx.AsyncClient) -> None:
    await ClienteSafeBrowsing(http, CHAVE_GOOGLE, 3).consultar([GOLPE.host])

    (requisicao,) = bases.do_google()
    assert requisicao.method == "POST"
    assert requisicao.url.path == "/v4/threatMatches:find"
    entradas = json.loads(requisicao.content)["threatInfo"]["threatEntries"]
    assert entradas == [{"url": f"http://{GOLPE.host}/"}, {"url": f"https://{GOLPE.host}/"}]


@pytest.mark.parametrize(
    ("resposta", "motivo"),
    [
        (httpx.Response(429), "limite"),
        (httpx.Response(500), "http"),
        (httpx.Response(403), "http"),
        (httpx.Response(200, content=b"isto nao e json"), "resposta"),
        (httpx.Response(200, json={"matches": [{"sem": "threat"}]}), "resposta"),
        (httpx.Response(200, json=["lista"]), "resposta"),
    ],
)
async def test_google_que_nao_responde_direito_vira_indisponivel(
    bases: Bases, http: httpx.AsyncClient, resposta: httpx.Response, motivo: str
) -> None:
    bases.google_responde = lambda _: resposta

    with pytest.raises(FonteIndisponivel) as erro:
        await ClienteSafeBrowsing(http, CHAVE_GOOGLE, 3).consultar([GOLPE.host])

    assert erro.value.motivo == motivo


async def test_timeout_do_google_nao_carrega_a_chave_na_excecao(
    bases: Bases, http: httpx.AsyncClient
) -> None:
    """A exceção do httpx traz a requisição, com a chave na query. A nossa não traz nada."""

    def estoura(requisicao: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("tempo esgotado", request=requisicao)

    bases.google_responde = estoura

    with pytest.raises(FonteIndisponivel) as erro:
        await ClienteSafeBrowsing(http, CHAVE_GOOGLE, 3).consultar([GOLPE.host])

    assert erro.value.motivo == "timeout"
    assert erro.value.__cause__ is None
    assert erro.value.__suppress_context__ is True
    assert CHAVE_GOOGLE not in repr(erro.value) + str(erro.value.args)


# ── VirusTotal ───────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("maliciosos", "suspeitos", "veredito"),
    [
        (0, 0, "limpo"),
        (0, 1, "limpo"),
        (1, 0, "suspeito"),
        (0, 2, "suspeito"),
        (2, 0, "malicioso"),
        (7, 3, "malicioso"),
    ],
)
async def test_virustotal_classifica_pelos_limiares_do_yaml(
    bases: Bases, http: httpx.AsyncClient, maliciosos: int, suspeitos: int, veredito: str
) -> None:
    bases.virustotal = {GOLPE.dominio: (maliciosos, suspeitos)}

    assert await ClienteVirusTotal(http, CHAVE_VT, 3, LIMIARES).consultar(GOLPE.dominio) == veredito


async def test_virustotal_recebe_o_dominio_no_caminho_e_a_chave_no_cabecalho(
    bases: Bases, http: httpx.AsyncClient
) -> None:
    await ClienteVirusTotal(http, CHAVE_VT, 3, LIMIARES).consultar(GOLPE.dominio)

    (requisicao,) = bases.do_virustotal()
    assert requisicao.method == "GET"
    assert str(requisicao.url) == f"https://www.virustotal.com/api/v3/domains/{GOLPE.dominio}"
    assert requisicao.headers["x-apikey"] == CHAVE_VT


async def test_dominio_que_o_virustotal_nao_conhece_e_limpo(http: httpx.AsyncClient) -> None:
    assert await ClienteVirusTotal(http, CHAVE_VT, 3, LIMIARES).consultar("novo.example") == "limpo"


@pytest.mark.parametrize(
    ("resposta", "motivo"),
    [
        (httpx.Response(429), "limite"),
        (httpx.Response(401), "http"),
        (httpx.Response(200, json={"data": {}}), "resposta"),
        (httpx.Response(200, content=b"<html>"), "resposta"),
    ],
)
async def test_virustotal_que_nao_responde_direito_vira_indisponivel(
    bases: Bases, http: httpx.AsyncClient, resposta: httpx.Response, motivo: str
) -> None:
    bases.virustotal_responde = lambda _: resposta

    with pytest.raises(FonteIndisponivel) as erro:
        await ClienteVirusTotal(http, CHAVE_VT, 3, LIMIARES).consultar(GOLPE.dominio)

    assert erro.value.motivo == motivo


# ── Verificador: as duas bases, cache, cota e teto ───────────────────────────────────────────


async def test_malicioso_nas_duas_bases(bases: Bases, verificador: VerificadorDeReputacao) -> None:
    bases.google_aponta = {GOLPE.host: 300}
    bases.virustotal = {GOLPE.dominio: (5, 0)}

    apontamentos, indisponivel = await _verificar_e_guardar(verificador, [GOLPE])

    assert apontamentos == [
        Apontamento(GOLPE.dominio, "safe_browsing", "malicioso"),
        Apontamento(GOLPE.dominio, "virustotal", "malicioso"),
    ]
    assert indisponivel is False


async def test_dominio_limpo_nao_gera_apontamento(
    bases: Bases, verificador: VerificadorDeReputacao
) -> None:
    bases.virustotal = {OUTRO.dominio: (0, 0)}

    assert await _verificar_e_guardar(verificador, [OUTRO]) == ([], False)


async def test_sem_alvo_nada_e_consultado(
    bases: Bases, verificador: VerificadorDeReputacao
) -> None:
    assert await _verificar_e_guardar(verificador, []) == ([], False)
    assert bases.requisicoes == []


async def test_sem_chave_a_base_nao_e_chamada_e_fica_indisponivel(
    bases: Bases,
    http: httpx.AsyncClient,
    reputacao_em_memoria: RepositorioReputacaoEmMemoria,
    relogio: RelogioFalso,
) -> None:
    sem_chaves = _verificador(http, reputacao_em_memoria, relogio, google=False, virustotal=False)

    assert await _verificar_e_guardar(sem_chaves, [GOLPE]) == ([], True)
    assert bases.requisicoes == []


async def test_uma_base_sem_chave_nao_impede_a_outra(
    bases: Bases,
    http: httpx.AsyncClient,
    reputacao_em_memoria: RepositorioReputacaoEmMemoria,
    relogio: RelogioFalso,
) -> None:
    bases.google_aponta = {GOLPE.host: 300}
    so_google = _verificador(http, reputacao_em_memoria, relogio, virustotal=False)

    apontamentos, indisponivel = await _verificar_e_guardar(so_google, [GOLPE])

    assert apontamentos == [Apontamento(GOLPE.dominio, "safe_browsing", "malicioso")]
    assert indisponivel is True
    assert bases.do_virustotal() == []


async def test_429_de_uma_base_marca_indisponivel_e_a_outra_vale(
    bases: Bases, verificador: VerificadorDeReputacao
) -> None:
    bases.google_aponta = {GOLPE.host: 300}
    bases.virustotal_responde = lambda _: httpx.Response(429)

    apontamentos, indisponivel = await _verificar_e_guardar(verificador, [GOLPE])

    assert apontamentos == [Apontamento(GOLPE.dominio, "safe_browsing", "malicioso")]
    assert indisponivel is True


async def test_base_lenta_estoura_o_teto_e_a_outra_vale(
    bases: Bases,
    reputacao_em_memoria: RepositorioReputacaoEmMemoria,
    relogio: RelogioFalso,
) -> None:
    """O VirusTotal trava; o Google responde. A etapa termina no teto, com o que o Google disse."""
    bases.google_aponta = {GOLPE.host: 300}

    async def responder(requisicao: httpx.Request) -> httpx.Response:
        if requisicao.url.host == "www.virustotal.com":
            await asyncio.sleep(5)
        return bases(requisicao)

    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as http:
        lento = VerificadorDeReputacao(
            safe_browsing=ClienteSafeBrowsing(http, CHAVE_GOOGLE, 3),
            virustotal=ClienteVirusTotal(http, CHAVE_VT, 3, LIMIARES),
            repositorio=reputacao_em_memoria,
            agora=relogio,
            timeout_s=0.05,
            virustotal_por_minuto=4,
            virustotal_por_dia=500,
        )
        inicio = asyncio.get_running_loop().time()
        resultado = await lento.verificar([GOLPE])
        duracao = asyncio.get_running_loop().time() - inicio

    assert list(resultado.apontamentos) == [
        Apontamento(GOLPE.dominio, "safe_browsing", "malicioso")
    ]
    assert resultado.indisponivel is True
    assert duracao < 1


async def test_cache_valido_do_virustotal_evita_a_segunda_consulta(
    bases: Bases, verificador: VerificadorDeReputacao, relogio: RelogioFalso
) -> None:
    bases.virustotal = {GOLPE.dominio: (3, 0)}
    await _verificar_e_guardar(verificador, [GOLPE])
    relogio.agora += timedelta(hours=23)

    apontamentos, indisponivel = await _verificar_e_guardar(verificador, [GOLPE])

    assert Apontamento(GOLPE.dominio, "virustotal", "malicioso") in apontamentos
    assert indisponivel is False
    assert len(bases.do_virustotal()) == 1


async def test_cache_vencido_do_virustotal_consulta_de_novo(
    bases: Bases, verificador: VerificadorDeReputacao, relogio: RelogioFalso
) -> None:
    bases.virustotal = {GOLPE.dominio: (3, 0)}
    await _verificar_e_guardar(verificador, [GOLPE])
    relogio.agora += timedelta(hours=24, seconds=1)
    bases.virustotal = {GOLPE.dominio: (0, 0)}

    apontamentos, _ = await _verificar_e_guardar(verificador, [GOLPE])

    assert apontamentos == []
    assert len(bases.do_virustotal()) == 2


async def test_aviso_do_google_vale_so_pelo_prazo_que_ele_deu(
    bases: Bases, verificador: VerificadorDeReputacao, relogio: RelogioFalso
) -> None:
    """Dentro do `cacheDuration`: o host segue apontado e não é perguntado de novo. Depois dele,
    a resposta antiga não vale mais: pergunta de novo, e vale o que o Google disser agora."""
    bases.google_aponta = {GOLPE.host: 300}
    await _verificar_e_guardar(verificador, [GOLPE])
    bases.google_aponta = {}

    relogio.agora += timedelta(seconds=299)
    dentro, _ = await _verificar_e_guardar(verificador, [GOLPE])
    assert Apontamento(GOLPE.dominio, "safe_browsing", "malicioso") in dentro
    assert len(bases.do_google()) == 1

    relogio.agora += timedelta(seconds=2)
    depois, _ = await _verificar_e_guardar(verificador, [GOLPE])
    assert depois == []
    assert len(bases.do_google()) == 2


async def test_resposta_limpa_do_google_nao_vai_para_o_cache(
    bases: Bases,
    verificador: VerificadorDeReputacao,
    reputacao_em_memoria: RepositorioReputacaoEmMemoria,
) -> None:
    await _verificar_e_guardar(verificador, [OUTRO])

    assert [chave for chave in reputacao_em_memoria.cache if chave[0] == "safe_browsing"] == []


async def test_cache_guarda_o_hash_e_nunca_o_dominio(
    bases: Bases,
    verificador: VerificadorDeReputacao,
    reputacao_em_memoria: RepositorioReputacaoEmMemoria,
) -> None:
    bases.google_aponta = {GOLPE.host: 300}
    bases.virustotal = {GOLPE.dominio: (3, 0)}

    await _verificar_e_guardar(verificador, [GOLPE])

    assert set(reputacao_em_memoria.cache) == {
        ("safe_browsing", chave_de_cache(GOLPE.host)),
        ("virustotal", chave_de_cache(GOLPE.dominio)),
    }
    assert "golpe" not in repr(reputacao_em_memoria.cache)


async def test_limite_diario_do_virustotal_atingido_pula_a_consulta(
    bases: Bases,
    http: httpx.AsyncClient,
    reputacao_em_memoria: RepositorioReputacaoEmMemoria,
    relogio: RelogioFalso,
) -> None:
    bases.google_aponta = {GOLPE.host: 300}
    bases.virustotal = {GOLPE.dominio: (9, 0)}
    no_limite = _verificador(http, reputacao_em_memoria, relogio, por_minuto=4, por_dia=1)
    await _verificar_e_guardar(no_limite, [OUTRO])
    relogio.agora += timedelta(minutes=5)

    apontamentos, indisponivel = await _verificar_e_guardar(no_limite, [GOLPE])

    assert apontamentos == [Apontamento(GOLPE.dominio, "safe_browsing", "malicioso")]
    assert indisponivel is True
    assert len(bases.do_virustotal()) == 1


async def test_limite_por_minuto_do_virustotal(
    bases: Bases, verificador: VerificadorDeReputacao, relogio: RelogioFalso
) -> None:
    """Quatro por minuto: três domínios passam, os três seguintes não, e no minuto seguinte sim."""
    primeiros = [Alvo(host=f"a{i}.example", dominio=f"a{i}.example") for i in range(3)]
    seguintes = [Alvo(host=f"b{i}.example", dominio=f"b{i}.example") for i in range(3)]

    assert (await verificador.verificar(primeiros)).indisponivel is False
    assert (await verificador.verificar(seguintes)).indisponivel is True
    assert len(bases.do_virustotal()) == 3

    relogio.agora += timedelta(minutes=1)
    assert (await verificador.verificar(seguintes)).indisponivel is False
    assert len(bases.do_virustotal()) == 6


async def test_banco_fora_nao_chama_o_virustotal_mas_o_google_responde(
    bases: Bases,
    verificador: VerificadorDeReputacao,
    reputacao_em_memoria: RepositorioReputacaoEmMemoria,
) -> None:
    """Sem conseguir contar, o limite do VirusTotal não é arriscado."""
    bases.google_aponta = {GOLPE.host: 300}
    reputacao_em_memoria.fora = True

    apontamentos, indisponivel = await _verificar_e_guardar(verificador, [GOLPE])

    assert apontamentos == [Apontamento(GOLPE.dominio, "safe_browsing", "malicioso")]
    assert indisponivel is True
    assert bases.do_virustotal() == []


async def test_endereco_numerico_vai_so_ao_google(
    bases: Bases, verificador: VerificadorDeReputacao
) -> None:
    numerico = Alvo(host="203.0.113.7", dominio="203.0.113.7", numerico=True)

    assert await _verificar_e_guardar(verificador, [numerico]) == ([], False)
    assert len(bases.do_google()) == 1
    assert bases.do_virustotal() == []


# ── Do apontamento ao fator ──────────────────────────────────────────────────────────────────


def test_pesos_do_yaml_sao_os_do_rfc() -> None:
    reputacao = carregar_regras().reputacao

    assert {sinal.id: sinal.peso for sinal in reputacao.sinais} == {
        "reputacao_safe_browsing": 40,
        "reputacao_virustotal_malicioso": 40,
        "reputacao_virustotal_suspeito": 20,
    }
    assert reputacao.maximo_de_dominios == 3


def test_frases_dizem_possivelmente_e_nao_levam_o_dominio() -> None:
    """Termos do Google: nunca afirmar que o endereço é perigoso com certeza."""
    reputacao = carregar_regras().reputacao
    google = reputacao.sinal("reputacao_safe_browsing")

    for frase in (
        google.descricao.renderizar(),
        google.no_link.renderizar(),
        reputacao.no_historico,
    ):
        assert "possivelmente" in frase
        assert "certeza" not in frase


def test_do_virustotal_sai_so_o_fator_mais_forte() -> None:
    reputacao = carregar_regras().reputacao
    apontamentos = [
        Apontamento("a.example", "virustotal", "suspeito"),
        Apontamento("b.example", "virustotal", "malicioso"),
        Apontamento("a.example", "safe_browsing", "malicioso"),
    ]

    fatores = fatores_de_reputacao(reputacao, apontamentos)

    assert [(f.tipo, f.categoria, f.peso) for f in fatores] == [
        ("reputacao", "reputacao_safe_browsing", 40),
        ("reputacao", "reputacao_virustotal_malicioso", 40),
    ]


@pytest.mark.parametrize(
    "texto",
    [
        "Oi, tudo bem? Veja em https://entrar.golpe-exemplo.example/a",
        "URGENTE: sua conta será bloqueada. Faça um PIX e confirme seu CPF em "
        "https://entrar.golpe-exemplo.example/a",
    ],
)
@pytest.mark.parametrize(
    "apontamentos",
    [
        [Apontamento("golpe-exemplo.example", "safe_browsing", "malicioso")],
        [Apontamento("golpe-exemplo.example", "virustotal", "suspeito")],
        [
            Apontamento("golpe-exemplo.example", "safe_browsing", "malicioso"),
            Apontamento("golpe-exemplo.example", "virustotal", "malicioso"),
        ],
    ],
)
def test_a_reputacao_so_sobe_o_nivel(texto: str, apontamentos: list[Apontamento]) -> None:
    ordem = {"BAIXO": 0, "MEDIO": 1, "ALTO": 2}
    servico = obter_servico_analise()

    sem = servico.analisar(texto)
    com = servico.analisar(texto, apontamentos)

    assert com.score > sem.score
    assert ordem[com.nivel_risco] >= ordem[sem.nivel_risco]
    assert ordem[com.nivel_motor] >= ordem[sem.nivel_motor]


def test_dominio_limpo_nas_bases_nao_baixa_nem_muda_nada() -> None:
    """Sem apontamento, a resposta é idêntica à do motor sozinho: silêncio não é atestado."""
    servico = obter_servico_analise()
    texto = "URGENTE: faça um PIX agora em https://entrar.golpe-exemplo.example/a"

    assert servico.analisar(texto, []) == servico.analisar(texto)


def test_bloco_de_links_diz_qual_base_apontou() -> None:
    servico = obter_servico_analise()
    texto = "Veja https://entrar.golpe-exemplo.example/a e https://outro-exemplo.example"
    apontamentos = [Apontamento("golpe-exemplo.example", "safe_browsing", "malicioso")]

    golpe, outro = servico.analisar(texto, apontamentos).links

    assert golpe.apontado_por == ["safe_browsing"]
    assert golpe.observacoes == ["apontado pelo Google Safe Browsing como possivelmente perigoso"]
    assert outro.apontado_por == []


# ── Só o domínio sai do processo ─────────────────────────────────────────────────────────────


def test_alvos_levam_so_host_e_dominio_registravel() -> None:
    servico = obter_servico_analise()
    texto = "Veja https://entrar.golpe-exemplo.example/pasta/CAMINHO-MARCADO?token=QUERY-MARCADA#F"

    assert servico.alvos_de_reputacao(texto) == [GOLPE]


def test_no_maximo_tres_dominios_por_analise() -> None:
    servico = obter_servico_analise()
    texto = " ".join(f"https://site{i}.example/x" for i in range(6))

    assert [alvo.host for alvo in servico.alvos_de_reputacao(texto)] == [
        "site0.example",
        "site1.example",
        "site2.example",
    ]


def test_endereco_oficial_nao_e_consultado_mas_marca_dentro_de_outro_dominio_e() -> None:
    """`itau.com.br` e os subdomínios dele são oficiais. `itau.com.br.golpe-exemplo.example` tem o
    nome da marca, mas o domínio registrável é outro: é consultado."""
    servico = obter_servico_analise()
    texto = (
        "https://www.itau.com.br/conta https://app.itau.com.br "
        "https://itau.com.br.golpe-exemplo.example/entrar"
    )

    assert servico.alvos_de_reputacao(texto) == [
        Alvo(host="itau.com.br.golpe-exemplo.example", dominio="golpe-exemplo.example")
    ]


@pytest.fixture
def app_com_bases(
    app: FastAPI,
    http: httpx.AsyncClient,
    reputacao_em_memoria: RepositorioReputacaoEmMemoria,
    relogio: RelogioFalso,
) -> FastAPI:
    app.dependency_overrides[obter_verificador_de_reputacao] = lambda: _verificador(
        http, reputacao_em_memoria, relogio
    )
    return app


LINK_MARCADO = "https://entrar.golpe-exemplo.example/pasta/CAMINHO-MARCADO?token=QUERY-MARCADA#FRAG"


async def test_caminho_query_e_fragmento_nunca_saem_na_requisicao(
    app_com_bases: FastAPI, cliente: AsyncClient, bases: Bases
) -> None:
    resposta = await cliente.post("/api/analises", json={"texto": f"Olha isto: {LINK_MARCADO}"})

    assert resposta.status_code == 200
    assert len(bases.do_google()) == 1
    assert len(bases.do_virustotal()) == 1
    saiu = bases.tudo_que_saiu()
    for marca in ("CAMINHO-MARCADO", "QUERY-MARCADA", "FRAG", "pasta", "token", "Olha isto"):
        assert marca not in saiu
    # O VirusTotal recebe o domínio registrável, sem o subdomínio.
    assert bases.do_virustotal()[0].url.path == "/api/v3/domains/golpe-exemplo.example"
    assert "entrar." not in str(bases.do_virustotal()[0].url)


async def test_api_soma_o_fator_e_sobe_o_nivel(
    app_com_bases: FastAPI, cliente: AsyncClient, bases: Bases
) -> None:
    texto = f"Olha isto: {LINK_MARCADO}"
    antes = (await cliente.post("/api/analises", json={"texto": texto})).json()
    bases.google_aponta = {GOLPE.host: 300}
    bases.virustotal = {GOLPE.dominio: (4, 0)}
    # Outro domínio no texto: o VirusTotal "limpo" de antes ficou no cache por 24 h.
    texto = texto.replace("golpe-exemplo", "golpe-exemplo2")
    bases.google_aponta = {"entrar.golpe-exemplo2.example": 300}
    bases.virustotal = {"golpe-exemplo2.example": (4, 0)}

    corpo = (await cliente.post("/api/analises", json={"texto": texto})).json()

    assert antes["nivel_risco"] == "BAIXO"
    assert corpo["nivel_risco"] == "ALTO"
    assert corpo["nivel_motor"] == "ALTO"
    assert corpo["score"] == antes["score"] + 80
    de_reputacao = [f for f in corpo["fatores"] if f["tipo"] == "reputacao"]
    assert [f["categoria"] for f in de_reputacao] == [
        "reputacao_safe_browsing",
        "reputacao_virustotal_malicioso",
    ]
    assert "golpe-exemplo2" not in json.dumps(de_reputacao)
    assert corpo["links"][0]["apontado_por"] == ["safe_browsing", "virustotal"]
    assert corpo["verificacao_externa_indisponivel"] is False


async def test_fator_de_reputacao_e_gravado_com_a_analise(
    app_com_bases: FastAPI, cliente: AsyncClient, bases: Bases, repositorio: Any
) -> None:
    bases.google_aponta = {GOLPE.host: 300}

    await cliente.post("/api/analises", json={"texto": f"Olha isto: {LINK_MARCADO}"})

    (registro,) = repositorio.registros
    assert ("reputacao", "reputacao_safe_browsing", 40) in [
        (f.tipo, f.categoria, f.peso) for f in registro.fatores
    ]


async def test_api_com_as_bases_fora_responde_igual_e_avisa(
    app_com_bases: FastAPI, cliente: AsyncClient, bases: Bases
) -> None:
    bases.google_responde = lambda _: httpx.Response(503)
    bases.virustotal_responde = lambda _: httpx.Response(429)

    resposta = await cliente.post("/api/analises", json={"texto": f"Olha isto: {LINK_MARCADO}"})

    corpo = resposta.json()
    assert resposta.status_code == 200
    assert corpo["verificacao_externa_indisponivel"] is True
    assert [f for f in corpo["fatores"] if f["tipo"] == "reputacao"] == []


async def test_sem_chave_configurada_a_flag_e_verdadeira_so_quando_ha_link(
    cliente: AsyncClient,
) -> None:
    """A app de teste não tem chave nenhuma: é a configuração de quem ainda não as cadastrou."""
    com_link = await cliente.post("/api/analises", json={"texto": f"Olha isto: {LINK_MARCADO}"})
    sem_link = await cliente.post("/api/analises", json={"texto": "Oi, tudo bem com você hoje?"})
    oficial = await cliente.post(
        "/api/analises", json={"texto": "Entre em https://www.itau.com.br"}
    )

    assert com_link.json()["verificacao_externa_indisponivel"] is True
    assert sem_link.json()["verificacao_externa_indisponivel"] is False
    assert oficial.json()["verificacao_externa_indisponivel"] is False


# ── A chave nunca aparece: log, Sentry, métrica ──────────────────────────────────────────────


async def test_chave_nunca_aparece_no_log(
    bases: Bases,
    verificador: VerificadorDeReputacao,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Com o log no nível mais falador e as duas bases falhando de três jeitos."""
    configurar_logs("DEBUG", "json")
    caplog.set_level(logging.DEBUG)

    def estoura(requisicao: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sem rede", request=requisicao)

    for falha in (lambda _: httpx.Response(500), lambda _: httpx.Response(429), estoura):
        bases.google_responde = bases.virustotal_responde = falha  # type: ignore[assignment]
        await verificador.verificar([Alvo(host=f"h{id(falha)}.example", dominio="d.example")])
    bases.google_responde = bases.virustotal_responde = None
    await verificador.verificar([GOLPE])

    saida = "\n".join(f"{registro.getMessage()} {registro.__dict__}" for registro in caplog.records)
    assert caplog.records, "o teste precisa ter capturado algum log"
    assert CHAVE_GOOGLE not in saida
    assert CHAVE_VT not in saida
    assert "golpe-exemplo" not in saida


def test_log_do_cliente_http_fica_desligado() -> None:
    """O httpx escreve em INFO a URL de cada chamada; a do Safe Browsing leva a chave."""
    configurar_logs("DEBUG", "json")

    assert logging.getLogger("httpx").disabled is True
    assert logging.getLogger("httpcore").disabled is True


def test_evento_do_sentry_nao_leva_a_chave() -> None:
    """Um erro numa chamada ao Safe Browsing: a mensagem da exceção e o nome do trecho de
    desempenho trazem a URL com `?key=`. Depois da limpeza, nada disso sobra."""
    url = f"https://safebrowsing.googleapis.com/v4/threatMatches:find?key={CHAVE_GOOGLE}"
    evento: dict[str, Any] = {
        "exception": {
            "values": [
                {
                    "type": "ReadTimeout",
                    "value": f"timeout em {url}",
                    "stacktrace": {"frames": [{"function": "consultar", "vars": {"url": url}}]},
                }
            ]
        },
        "spans": [
            {"op": "http.client", "description": f"POST {url}", "data": {"url": url}},
            {"op": "http.client", "description": "GET https://www.virustotal.com/api/v3/domains/x"},
        ],
        "breadcrumbs": {"values": [{"category": "httplib", "data": {"url": url}}]},
        "extra": {"url": url},
    }

    limpo = json.dumps(limpar_evento(evento))  # type: ignore[arg-type]

    assert CHAVE_GOOGLE not in limpo
    assert "key=" not in limpo
    assert "ReadTimeout" in limpo
    assert "POST https://safebrowsing.googleapis.com/v4/threatMatches:find" in limpo


def _contagem(nome: str, **rotulos: str) -> float:
    return REGISTRO.get_sample_value(nome, rotulos) or 0.0


async def test_metricas_contam_por_base_e_resultado_sem_o_dominio(
    bases: Bases, verificador: VerificadorDeReputacao
) -> None:
    consultas = "verifyscan_reputacao_consultas_total"
    falhas = "verifyscan_reputacao_falhas_total"
    antes = (
        _contagem(consultas, fonte="safe_browsing", resultado="malicioso"),
        _contagem(consultas, fonte="virustotal", resultado="suspeito"),
        _contagem(consultas, fonte="virustotal", resultado="cache"),
        _contagem(falhas, fonte="virustotal", motivo="limite"),
    )
    bases.google_aponta = {GOLPE.host: 300}
    bases.virustotal = {GOLPE.dominio: (1, 0)}

    await _verificar_e_guardar(verificador, [GOLPE])
    await _verificar_e_guardar(verificador, [GOLPE])
    bases.virustotal_responde = lambda _: httpx.Response(429)
    await _verificar_e_guardar(verificador, [OUTRO])

    depois = (
        _contagem(consultas, fonte="safe_browsing", resultado="malicioso"),
        _contagem(consultas, fonte="virustotal", resultado="suspeito"),
        _contagem(consultas, fonte="virustotal", resultado="cache"),
        _contagem(falhas, fonte="virustotal", motivo="limite"),
    )
    assert [d - a for d, a in zip(depois, antes, strict=True)] == [1, 1, 1, 1]
    texto = exposicao().decode()
    assert "golpe-exemplo" not in texto
    assert "outro-exemplo" not in texto


# ── Histórico e configuração ─────────────────────────────────────────────────────────────────


def test_no_historico_a_reputacao_vira_uma_linha_neutra() -> None:
    """Sem citar a base e sem afirmar o estado de hoje: é o registro do dia da análise."""
    gravados = [
        FatorDoHistorico("urgencia", "A mensagem cria urgência.", 15),
        FatorDoHistorico("reputacao_safe_browsing", "O Google Safe Browsing aponta…", 40),
        FatorDoHistorico("reputacao_virustotal_suspeito", "Um serviço… VirusTotal…", 20),
    ]

    urgencia, reputacao = _fatores_do_historico(gravados)

    assert urgencia.categoria == "urgencia"
    assert reputacao.categoria == "reputacao"
    assert reputacao.peso == 60
    assert reputacao.descricao == (
        "Na data desta análise, uma base de reputação externa apontava este domínio como "
        "possivelmente perigoso."
    )
    assert "Google" not in reputacao.descricao
    assert "VirusTotal" not in reputacao.descricao


def test_chaves_sao_opcionais_e_vazia_e_ausente() -> None:
    padrao = settings_de_teste()
    vazias = settings_de_teste(safe_browsing_api_key="", virustotal_api_key="  ")
    com = settings_de_teste(safe_browsing_api_key=CHAVE_GOOGLE)

    assert padrao.safe_browsing_api_key is None
    assert padrao.virustotal_api_key is None
    assert vazias.safe_browsing_api_key is None
    assert vazias.virustotal_api_key is None
    assert CHAVE_GOOGLE not in repr(com)


@pytest.mark.parametrize(
    ("campo", "valor"),
    [("virustotal_por_minuto", 5), ("virustotal_por_dia", 501), ("reputacao_timeout_s", 3.5)],
)
def test_limites_so_podem_baixar(campo: str, valor: float) -> None:
    """Os limites do VirusTotal são dos termos de uso, e o teto de tempo é da invariante 8."""
    with pytest.raises(ValidationError):
        settings_de_teste(**{campo: valor})
