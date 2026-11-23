"""Id da requisição e o log por requisição (ADR-0026).

O log leva o TEMPLATE da rota, nunca o caminho cru: o caminho tem o id da análise, e um caminho
que não existe pode ter qualquer coisa que alguém digitou.
"""

import logging
import uuid

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from tests.conftest import SERVICO_OK, verificador_falso

ID_VALIDO = "3f0c2b0e-8f55-4d0a-9d0e-0a1b2c3d4e5f"
MARCA = "SEGREDO-DO-TESTE-123"


def _da_requisicao(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if getattr(r, "evento", None) == "requisicao"]


async def test_gera_um_id_quando_nao_vem(cliente: AsyncClient) -> None:
    resposta = await cliente.post("/api/analises", json={"texto": "oi, tudo bem?"})

    recebido = resposta.headers["x-request-id"]
    assert str(uuid.UUID(recebido)) == recebido


async def test_cada_requisicao_tem_o_seu(cliente: AsyncClient) -> None:
    primeira = await cliente.post("/api/analises", json={"texto": "oi, tudo bem?"})
    segunda = await cliente.post("/api/analises", json={"texto": "oi, tudo bem?"})

    assert primeira.headers["x-request-id"] != segunda.headers["x-request-id"]


async def test_aceita_o_id_do_proxy_se_for_uuid(cliente: AsyncClient) -> None:
    resposta = await cliente.post(
        "/api/analises", json={"texto": "oi, tudo bem?"}, headers={"X-Request-ID": ID_VALIDO}
    )

    assert resposta.headers["x-request-id"] == ID_VALIDO


@pytest.mark.parametrize(
    "recebido",
    [
        MARCA,
        "",
        "123",
        # Formas que o `uuid.UUID` aceita, mas que não são a forma canônica: recusadas, para o
        # campo do log ter sempre o mesmo desenho.
        ID_VALIDO.replace("-", ""),
        "{" + ID_VALIDO + "}",
        "urn:uuid:" + ID_VALIDO,
        ID_VALIDO + " " + MARCA,
    ],
)
async def test_recusa_o_que_nao_e_uuid_e_gera_outro(
    recebido: str, cliente: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app"):
        resposta = await cliente.post(
            "/api/analises", json={"texto": "oi, tudo bem?"}, headers={"X-Request-ID": recebido}
        )

    devolvido = resposta.headers["x-request-id"]
    assert devolvido != recebido
    assert str(uuid.UUID(devolvido)) == devolvido
    assert MARCA not in caplog.text
    assert MARCA not in str([r.__dict__ for r in caplog.records])


async def test_um_log_por_requisicao_com_o_template_da_rota(
    cliente: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    id_da_analise = str(uuid.uuid4())
    with caplog.at_level(logging.INFO, logger="app"):
        resposta = await cliente.delete(f"/api/historico/{id_da_analise}?x={MARCA}")

    [registro] = _da_requisicao(caplog)
    campos = registro.campos  # type: ignore[attr-defined]
    assert campos["metodo"] == "DELETE"
    assert campos["rota"] == "/api/historico/{analise_id}"
    assert campos["status"] == resposta.status_code == 401
    assert isinstance(campos["duracao_ms"], int)
    assert set(campos) == {"metodo", "rota", "status", "duracao_ms"}
    # Nem o id do caminho, nem a query string.
    tudo = caplog.text + str([r.__dict__ for r in caplog.records])
    assert id_da_analise not in tudo
    assert MARCA not in tudo


async def test_caminho_que_nao_existe_nao_vai_para_o_log(
    cliente: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app"):
        resposta = await cliente.get(f"/{MARCA}/qualquer")

    assert resposta.status_code == 404
    [registro] = _da_requisicao(caplog)
    assert registro.campos["rota"] == "nao_mapeada"  # type: ignore[attr-defined]
    assert MARCA not in caplog.text + str([r.__dict__ for r in caplog.records])


async def test_os_logs_da_requisicao_levam_o_id_dela(
    cliente: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    from app.core.logs import request_id_atual

    vistos: list[str | None] = []

    class Espia(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            vistos.append(request_id_atual.get())

    espia = Espia()
    logging.getLogger("app").addHandler(espia)
    try:
        with caplog.at_level(logging.INFO, logger="app"):
            await cliente.post(
                "/api/analises",
                json={"texto": "oi, tudo bem?"},
                headers={"X-Request-ID": ID_VALIDO},
            )
    finally:
        logging.getLogger("app").removeHandler(espia)

    assert vistos
    assert set(vistos) == {ID_VALIDO}
    # Fora da requisição, o contexto volta a ficar vazio.
    assert request_id_atual.get() is None


async def test_health_nao_e_logado(
    app: FastAPI, cliente: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    from app.api.deps import obter_verificador_postgres, obter_verificador_redis

    app.dependency_overrides[obter_verificador_postgres] = verificador_falso(SERVICO_OK)
    app.dependency_overrides[obter_verificador_redis] = verificador_falso(SERVICO_OK)
    with caplog.at_level(logging.INFO, logger="app"):
        resposta = await cliente.get("/health")

    assert resposta.status_code == 200
    # O id continua saindo: quem não é logado ainda pode ser rastreado pelo cabeçalho.
    assert "x-request-id" in resposta.headers
    assert _da_requisicao(caplog) == []


async def test_erro_nao_tratado_e_logado_com_500_tipo_e_pilha_sem_a_mensagem(
    app: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    from httpx import ASGITransport

    from app.api.deps import obter_orquestrador
    from app.core.logs import FormatadorJSON

    class Quebrado:
        async def analisar(self, *args: object) -> None:
            raise RuntimeError(f"valor recebido: {MARCA}")

    app.dependency_overrides[obter_orquestrador] = lambda: Quebrado()
    transporte = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transporte, base_url="http://teste") as cliente:
        with caplog.at_level(logging.INFO, logger="app"):
            resposta = await cliente.post("/api/analises", json={"texto": "oi, tudo bem?"})

    assert resposta.status_code == 500
    [registro] = _da_requisicao(caplog)
    assert registro.levelno == logging.ERROR
    assert registro.campos["status"] == 500  # type: ignore[attr-defined]
    linha = FormatadorJSON().format(registro)
    assert "RuntimeError" in linha
    assert "analisar" in linha
    assert MARCA not in linha
