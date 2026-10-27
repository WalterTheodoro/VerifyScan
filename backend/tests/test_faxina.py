"""Faxina oportunista: análises vencidas perdem o dono e o texto, sessões vencidas somem (ADR-0019).

Roda sem agendador, na subida e a cada listagem do histórico, com o teto do registro, e nunca
derruba quem a chamou. O SQL é provado contra o Postgres em `tests/integracao/test_conta.py`.
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import obter_repositorio_sessoes, obter_usuario_atual
from app.services.historico import faxina
from app.services.repositorio_usuarios import UsuarioAutenticado
from tests.conftest import (
    RelogioFalso,
    RepositorioHistoricoEmMemoria,
    RepositorioSessoesEmMemoria,
    SessaoEmMemoria,
)

MARIA = UsuarioAutenticado(id=uuid.uuid4(), nome="Maria", email="maria@exemplo.com")
SEGREDO = "XYZZY4242"


@pytest.fixture
async def navegador(app: FastAPI) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[obter_usuario_atual] = lambda: MARIA
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://teste") as cliente:
        yield cliente


def _sessao(relogio: RelogioFalso, expira_em_horas: float) -> SessaoEmMemoria:
    """Sessão de uma conta qualquer: a faxina não olha o dono."""
    return SessaoEmMemoria(
        usuario_id=uuid.uuid4(),
        token_hash=uuid.uuid4().hex * 2,
        expira_em=relogio() + timedelta(hours=expira_em_horas),
    )


async def test_listar_apaga_as_sessoes_vencidas_de_todas_as_contas(
    navegador: AsyncClient, sessoes: RepositorioSessoesEmMemoria, relogio: RelogioFalso
) -> None:
    valida = _sessao(relogio, expira_em_horas=1)
    sessoes.sessoes = [_sessao(relogio, -1), valida, _sessao(relogio, 0)]

    assert (await navegador.get("/api/historico")).status_code == 200

    # Vencida é `expira_em <= now()`, a mesma borda de quem autentica (`> now()`).
    assert sessoes.sessoes == [valida]


class SessoesQueNaoLimpam(RepositorioSessoesEmMemoria):
    async def apagar_todas_vencidas(self) -> int:
        raise RuntimeError(f"falhou {SEGREDO}")


async def test_limpeza_de_sessoes_que_falha_so_loga_e_a_listagem_continua(
    app: FastAPI, navegador: AsyncClient, relogio: RelogioFalso, caplog: pytest.LogCaptureFixture
) -> None:
    app.dependency_overrides[obter_repositorio_sessoes] = lambda: SessoesQueNaoLimpam(relogio)

    with caplog.at_level(logging.WARNING):
        resposta = await navegador.get("/api/historico")

    assert resposta.status_code == 200
    assert "RuntimeError" in caplog.text
    assert SEGREDO not in caplog.text


class SessoesLentas(RepositorioSessoesEmMemoria):
    async def apagar_todas_vencidas(self) -> int:
        await asyncio.sleep(3600)
        raise AssertionError("o timeout deveria ter cortado antes")


async def test_faxina_respeita_o_teto_e_nunca_levanta(
    relogio: RelogioFalso,
    historico: RepositorioHistoricoEmMemoria,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Um teto só para os dois passos: a listagem não espera mais que antes desta fatia."""
    with caplog.at_level(logging.WARNING):
        await faxina(historico, SessoesLentas(relogio), historico_dias=7, timeout_s=0.05)

    assert historico.desvinculacoes == 1
    assert "TimeoutError" in caplog.text
