"""POST /api/analises registra a análise — e nunca falha por causa do registro (ADR-0012).

Mesma filosofia das invariantes 3 e 4: o banco é necessário para auditoria, não para responder.
Se o registro falhar ou estourar o tempo, a transação é descartada, vira WARNING e a resposta sai
idêntica.
"""

import asyncio
import dataclasses
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import obter_repositorio_analises, obter_repositorio_sessoes
from app.core.config import get_settings
from app.services.repositorio_analises import RegistroAnalise
from app.services.repositorio_usuarios import UsuarioAutenticado
from tests.conftest import RelogioFalso, RepositorioAnalisesEmMemoria, RepositorioSessoesEmMemoria
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
    mensagem nem os links (a query da URL pode carregar e-mail ou token da vítima). O dono
    (ADR-0015) é o único campo que entrou, e é um id, não conteúdo."""
    campos = {campo.name for campo in dataclasses.fields(RegistroAnalise)}

    assert campos == {"score", "nivel_risco", "tipo_input", "fatores", "usuario_id"}


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


# ─── registro com dono (ADR-0015) ─────────────────────────────────────────────────────────
# A rota só lê o cookie. Quem resolve o dono é o orquestrador, depois da análise e dentro do
# mesmo teto do registro: o resultado nunca espera pela sessão.

CADASTRO = {"nome": "Maria", "email": "maria@exemplo.com", "senha": "uma senha boa"}


@pytest.fixture
async def navegador(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Cliente que guarda cookie, em https: o httpx não devolve cookie Secure em http."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://teste") as cliente:
        yield cliente


class SessoesQueFalham(RepositorioSessoesEmMemoria):
    async def buscar_usuario(self, token_hash: str) -> UsuarioAutenticado | None:
        raise RuntimeError(f"falhou ao consultar {SEGREDO}")


class SessoesLentas(RepositorioSessoesEmMemoria):
    async def buscar_usuario(self, token_hash: str) -> UsuarioAutenticado | None:
        await asyncio.sleep(3600)
        raise AssertionError("o timeout deveria ter cortado antes")


async def _cadastrar(navegador: AsyncClient) -> None:
    """Cadastro deixa o navegador logado: conta e sessão nascem juntas (ADR-0013)."""
    resposta = await navegador.post("/api/auth/cadastro", json=CADASTRO)
    assert resposta.status_code == 201


async def test_sem_cookie_grava_anonima_e_nao_salva_no_historico(
    navegador: AsyncClient, repositorio: RepositorioAnalisesEmMemoria
) -> None:
    corpo = (await navegador.post("/api/analises", json={"texto": GOLPE_DE_PIX})).json()

    assert corpo["salva_no_historico"] is False
    assert repositorio.registros[0].usuario_id is None


async def test_com_sessao_valida_grava_com_dono(
    navegador: AsyncClient,
    repositorio: RepositorioAnalisesEmMemoria,
    sessoes: RepositorioSessoesEmMemoria,
) -> None:
    await _cadastrar(navegador)

    corpo = (await navegador.post("/api/analises", json={"texto": GOLPE_DE_PIX})).json()

    assert corpo["salva_no_historico"] is True
    assert repositorio.registros[0].usuario_id == sessoes.sessoes[0].usuario_id


async def test_com_sessao_vencida_grava_anonima(
    navegador: AsyncClient, repositorio: RepositorioAnalisesEmMemoria, relogio: RelogioFalso
) -> None:
    await _cadastrar(navegador)
    relogio.agora += timedelta(days=7)

    corpo = (await navegador.post("/api/analises", json={"texto": GOLPE_DE_PIX})).json()

    assert corpo["salva_no_historico"] is False
    assert repositorio.registros[0].usuario_id is None


async def test_consulta_da_sessao_com_erro_grava_anonima(
    app: FastAPI,
    navegador: AsyncClient,
    repositorio: RepositorioAnalisesEmMemoria,
    relogio: RelogioFalso,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _cadastrar(navegador)
    app.dependency_overrides[obter_repositorio_sessoes] = lambda: SessoesQueFalham(relogio)

    with caplog.at_level(logging.WARNING):
        resposta = await navegador.post("/api/analises", json={"texto": GOLPE_DE_PIX})

    assert resposta.status_code == 200
    assert resposta.json()["salva_no_historico"] is False
    assert len(repositorio.registros) == 1
    assert repositorio.registros[0].usuario_id is None
    assert "RuntimeError" in caplog.text
    assert SEGREDO not in caplog.text
    assert "PIX" not in caplog.text


async def test_sessao_lenta_estoura_o_teto_do_registro_e_nada_e_gravado(
    app: FastAPI,
    navegador: AsyncClient,
    repositorio: RepositorioAnalisesEmMemoria,
    relogio: RelogioFalso,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Um teto só para resolver o dono e gravar: a invariante 8 não ganha etapa nova."""
    await _cadastrar(navegador)
    app.dependency_overrides[obter_repositorio_sessoes] = lambda: SessoesLentas(relogio)
    monkeypatch.setattr(get_settings(), "timeout_persistencia_s", 0.05)

    with caplog.at_level(logging.WARNING):
        resposta = await navegador.post("/api/analises", json={"texto": GOLPE_DE_PIX})

    assert resposta.status_code == 200
    assert resposta.json()["salva_no_historico"] is False
    assert repositorio.registros == []
    assert "TimeoutError" in caplog.text


async def test_registro_que_estoura_o_tempo_logado_nao_salva_no_historico(
    app: FastAPI,
    navegador: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _cadastrar(navegador)
    app.dependency_overrides[obter_repositorio_analises] = RepositorioLento
    monkeypatch.setattr(get_settings(), "timeout_persistencia_s", 0.05)

    resposta = await navegador.post("/api/analises", json={"texto": GOLPE_DE_PIX})

    assert resposta.status_code == 200
    assert resposta.json()["salva_no_historico"] is False
