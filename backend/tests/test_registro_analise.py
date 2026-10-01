"""POST /api/analises registra a análise — e nunca falha por causa do registro (ADR-0012).

Mesma filosofia das invariantes 3 e 4: o banco é necessário para auditoria, não para responder.
Se o registro falhar ou estourar o tempo, a transação é descartada, vira WARNING e a resposta sai
idêntica.
"""

import asyncio
import dataclasses
import logging
import uuid

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.api.deps import obter_repositorio_analises
from app.core.config import get_settings
from app.services.repositorio_analises import RegistroAnalise
from tests.conftest import RepositorioAnalisesEmMemoria
from tests.test_api_analises import GOLPE_DE_PIX

SEGREDO = "XYZZY4242"


class RepositorioQueFalha:
    async def registrar(self, registro: RegistroAnalise) -> uuid.UUID:
        # A mensagem da exceção carrega conteúdo: o log não pode reproduzi-la.
        raise RuntimeError(f"falhou ao gravar {SEGREDO}")


class RepositorioLento:
    async def registrar(self, registro: RegistroAnalise) -> uuid.UUID:
        await asyncio.sleep(3600)
        raise AssertionError("o timeout deveria ter cortado antes")


async def test_analise_valida_e_registrada(
    cliente: AsyncClient, repositorio: RepositorioAnalisesEmMemoria
) -> None:
    corpo = (await cliente.post("/api/analises", json={"texto": GOLPE_DE_PIX})).json()

    assert len(repositorio.registros) == 1
    registro = repositorio.registros[0]
    assert registro.score == corpo["score"]
    assert registro.nivel_risco == corpo["nivel_risco"]
    assert registro.tipo_input == "texto"
    assert [f.model_dump() for f in registro.fatores] == corpo["fatores"]


async def test_entrada_recusada_nao_e_registrada(
    cliente: AsyncClient, repositorio: RepositorioAnalisesEmMemoria
) -> None:
    resposta = await cliente.post("/api/analises", json={"texto": "   "})

    assert resposta.status_code == 422
    assert repositorio.registros == []


def test_registro_nao_tem_campo_para_texto_nem_url() -> None:
    """ADR-0006 e ADR-0009 garantidos no tipo: o repositório não tem por onde receber a
    mensagem nem os links (a query da URL pode carregar e-mail ou token da vítima)."""
    campos = {campo.name for campo in dataclasses.fields(RegistroAnalise)}

    assert campos == {"score", "nivel_risco", "tipo_input", "fatores"}


async def _corpo_de_referencia(cliente: AsyncClient) -> dict[str, object]:
    resposta = await cliente.post("/api/analises", json={"texto": GOLPE_DE_PIX})
    assert resposta.status_code == 200
    corpo: dict[str, object] = resposta.json()
    return corpo


async def test_falha_ao_registrar_nao_derruba_a_analise(
    app: FastAPI, cliente: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    referencia = await _corpo_de_referencia(cliente)
    app.dependency_overrides[obter_repositorio_analises] = RepositorioQueFalha

    with caplog.at_level(logging.WARNING):
        resposta = await cliente.post("/api/analises", json={"texto": GOLPE_DE_PIX})

    assert resposta.status_code == 200
    assert resposta.json() == referencia
    avisos = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(avisos) == 1
    assert "RuntimeError" in avisos[0].getMessage()
    # Nem a mensagem da exceção nem o texto do usuário vão para o log.
    assert SEGREDO not in caplog.text
    assert "PIX" not in caplog.text


async def test_registro_que_estoura_o_tempo_nao_derruba_a_analise(
    app: FastAPI,
    cliente: AsyncClient,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    referencia = await _corpo_de_referencia(cliente)
    app.dependency_overrides[obter_repositorio_analises] = RepositorioLento
    monkeypatch.setattr(get_settings(), "timeout_persistencia_s", 0.05)

    with caplog.at_level(logging.WARNING):
        resposta = await cliente.post("/api/analises", json={"texto": GOLPE_DE_PIX})

    assert resposta.status_code == 200
    assert resposta.json() == referencia
    assert "TimeoutError" in caplog.text
