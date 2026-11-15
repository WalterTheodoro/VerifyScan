"""O IP de quem pediu nunca é gravado nem logado (fatia 10, ADR-0024).

O que vai para a cota e para o limite de login é o HMAC do IP com um segredo do servidor. Aqui se
confere o que sai da aplicação: as chaves guardadas e todo registro de log, em DEBUG, de todos os
loggers (o `caplog` escuta no root).
"""

import logging

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import obter_analisador_ia, obter_consumo
from app.core.config import get_settings
from app.core.ip import chave_hmac
from app.formulator.analisador import AnalisadorIA
from app.formulator.cliente import ConsumoDaIA
from tests.conftest import ClienteIAFalso, RepositorioUsoEmMemoria, settings_de_teste
from tests.test_api_analises import GOLPE_DE_PIX

IP = "203.0.113.77"
IP_REPASSADO = "198.51.100.42"
_CONSUMO = Depends(obter_consumo)


@pytest.fixture
def com_ia(app: FastAPI) -> FastAPI:
    app.dependency_overrides[get_settings] = lambda: settings_de_teste(ia_cota_sem_conta=5)

    def analisador(consumo: ConsumoDaIA = _CONSUMO) -> AnalisadorIA:
        return AnalisadorIA(ClienteIAFalso(), 15, consumo)

    app.dependency_overrides[obter_analisador_ia] = analisador
    return app


async def test_a_chave_da_cota_e_o_hmac_e_nao_o_ip(
    com_ia: FastAPI, cliente: AsyncClient, uso: RepositorioUsoEmMemoria
) -> None:
    await cliente.post(
        "/api/analises", json={"texto": GOLPE_DE_PIX}, headers={"x-forwarded-for": IP}
    )

    ((_, chave, _),) = uso.usos
    segredo = settings_de_teste().ip_hmac_segredo.get_secret_value()
    assert chave == f"ip:{chave_hmac(segredo, IP)}"
    assert IP not in chave


async def test_o_ip_nao_aparece_em_nenhum_log(
    com_ia: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    segredo_proxy = settings_de_teste().proxy_segredo.get_secret_value()
    repassado = {"x-verifyscan-ip": IP_REPASSADO, "x-verifyscan-segredo": segredo_proxy}
    async with AsyncClient(transport=ASGITransport(app=com_ia), base_url="https://teste") as nav:
        with caplog.at_level(logging.DEBUG):
            await nav.post(
                "/api/analises", json={"texto": GOLPE_DE_PIX}, headers={"x-forwarded-for": IP}
            )
            await nav.post("/api/analises", json={"texto": GOLPE_DE_PIX}, headers=repassado)
            await nav.post(
                "/api/auth/login",
                json={"email": "ninguem@exemplo.com", "senha": "senha errada"},
                headers={"x-forwarded-for": IP},
            )
            await nav.post(
                "/api/auth/cadastro",
                json={"nome": "Maria", "email": "maria@exemplo.com", "senha": "senha boa 123"},
                headers={"x-forwarded-for": IP},
            )

    assert caplog.records, "o teste precisa capturar algum log, senão não prova nada"
    assert IP not in caplog.text
    assert IP_REPASSADO not in caplog.text
    assert segredo_proxy not in caplog.text


def test_o_log_de_acesso_do_uvicorn_sai_desligado(app: FastAPI) -> None:
    """Cada linha dele começa pelo endereço de quem pediu, que o uvicorn tira do
    `X-Forwarded-For` quando confia no proxy: o IP do visitante iria para o log."""
    assert logging.getLogger("uvicorn.access").disabled
