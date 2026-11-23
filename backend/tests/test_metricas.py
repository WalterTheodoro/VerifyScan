"""GET /metrics (ADR-0026): só com o token, e sem token configurado a rota nem existe."""

import logging

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.config import get_settings
from tests.conftest import SERVICO_OK, settings_de_teste, verificador_falso
from tests.test_api_analises import GOLPE_DE_PIX

TOKEN = "token-de-teste-das-metricas-0123456789"
CERTO = {"Authorization": f"Bearer {TOKEN}"}


def _com_token(app: FastAPI) -> None:
    app.dependency_overrides[get_settings] = lambda: settings_de_teste(metrics_token=TOKEN)


def _amostra(corpo: str, comeco: str) -> float:
    """O valor da linha que começa por `comeco`, ou 0 se a série ainda não existe."""
    for linha in corpo.splitlines():
        if linha.startswith(comeco):
            return float(linha.rsplit(" ", 1)[1])
    return 0.0


async def test_sem_token_configurado_a_rota_responde_404(cliente: AsyncClient) -> None:
    sem_nada = await cliente.get("/metrics")
    com_um_token = await cliente.get("/metrics", headers=CERTO)

    assert sem_nada.status_code == 404
    assert com_um_token.status_code == 404


@pytest.mark.parametrize(
    "cabecalhos",
    [
        {},
        {"Authorization": "Bearer token-errado"},
        {"Authorization": f"Bearer {TOKEN}x"},
        {"Authorization": f"Basic {TOKEN}"},
        {"Authorization": TOKEN},
        {"Authorization": "Bearer "},
        # Fora do ASCII: a comparação em tempo constante não pode quebrar com 500.
        # Em bytes: o cliente de teste só aceita texto ASCII, e um navegador manda o que quiser.
        {"Authorization": "Bearer tökén".encode("latin-1")},
    ],
    ids=["sem", "errado", "quase", "basic", "sem-bearer", "vazio", "nao-ascii"],
)
async def test_token_errado_responde_401(
    cabecalhos: dict[str, str | bytes], app: FastAPI, cliente: AsyncClient
) -> None:
    _com_token(app)

    resposta = await cliente.get("/metrics", headers=cabecalhos)

    assert resposta.status_code == 401
    assert "verifyscan_" not in resposta.text


async def test_token_certo_responde_200_no_formato_do_prometheus(
    app: FastAPI, cliente: AsyncClient
) -> None:
    _com_token(app)

    resposta = await cliente.get("/metrics", headers=CERTO)

    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/plain")
    for nome, tipo in (
        ("verifyscan_analises_total", "counter"),
        ("verifyscan_analise_duracao_segundos", "histogram"),
        ("verifyscan_ia_falhas_total", "counter"),
        ("verifyscan_ia_subiu_nivel_total", "counter"),
        ("verifyscan_cota_excedida_total", "counter"),
        ("verifyscan_gasto_ia_dolares_hoje", "gauge"),
        ("http_requisicoes_total", "counter"),
        ("http_duracao_segundos", "histogram"),
    ):
        assert f"# TYPE {nome} {tipo}" in resposta.text


async def test_os_contadores_sobem_depois_de_uma_analise(
    app: FastAPI, cliente: AsyncClient
) -> None:
    _com_token(app)
    analises = 'verifyscan_analises_total{nivel_final="ALTO",tipo="texto"}'
    requisicoes = 'http_requisicoes_total{metodo="POST",rota="/api/analises",status="200"}'
    antes = (await cliente.get("/metrics", headers=CERTO)).text

    await cliente.post("/api/analises", json={"texto": GOLPE_DE_PIX})
    depois = (await cliente.get("/metrics", headers=CERTO)).text

    assert _amostra(depois, analises) == _amostra(antes, analises) + 1
    assert _amostra(depois, requisicoes) == _amostra(antes, requisicoes) + 1


async def test_a_coleta_nao_conta_a_si_mesma_nem_o_health(
    app: FastAPI, cliente: AsyncClient
) -> None:
    from app.api.deps import obter_verificador_postgres, obter_verificador_redis

    _com_token(app)
    app.dependency_overrides[obter_verificador_postgres] = verificador_falso(SERVICO_OK)
    app.dependency_overrides[obter_verificador_redis] = verificador_falso(SERVICO_OK)

    await cliente.get("/health")
    corpo = (await cliente.get("/metrics", headers=CERTO)).text

    assert 'rota="/metrics"' not in corpo
    assert 'rota="/health"' not in corpo


async def test_o_token_nao_vai_para_o_log(
    app: FastAPI, cliente: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    _com_token(app)

    with caplog.at_level(logging.DEBUG):
        await cliente.get("/metrics", headers=CERTO)
        await cliente.get("/metrics", headers={"Authorization": "Bearer token-errado"})

    tudo = caplog.text + str([r.__dict__ for r in caplog.records])
    assert TOKEN not in tudo
    assert "token-errado" not in tudo


def test_token_curto_demais_nao_sobe() -> None:
    with pytest.raises(ValueError):
        settings_de_teste(metrics_token="curto")


def test_token_vazio_e_o_mesmo_que_nao_ter() -> None:
    assert settings_de_teste(metrics_token="").metrics_token is None
