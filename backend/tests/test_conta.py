"""Trocar senha e excluir a conta, com repositórios em memória (ADR-0019).

Aqui se confere o HTTP: status, `detail` em pt-BR, cookie e quais sessões sobrevivem. O SQL — a
transação da troca e os CASCADE da exclusão — é provado contra o Postgres em
`tests/integracao/test_conta.py`.

A regra que atravessa o arquivo: senha errada é **400**, nunca 401. O frontend trata 401 como
"deslogado" e trocaria a tela por "Entrar".
"""

import asyncio
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import obter_repositorio_usuarios
from app.core.config import get_settings
from app.services.repositorio_usuarios import CredenciaisArmazenadas
from tests.conftest import (
    RepositorioSessoesEmMemoria,
    RepositorioUsuariosEmMemoria,
    settings_de_teste,
)
from tests.test_api_autenticacao import CADASTRO, LOGIN, _atributos, _cookie_de_sessao

SENHA_NOVA = "outra senha boa"
SENHA_ERRADA = {"detail": "A senha atual não confere."}


async def _navegador(app: FastAPI) -> AsyncClient:
    """Cliente que guarda cookie, em https: o httpx não devolve cookie Secure em http."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="https://teste")


@pytest.fixture
async def maria(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Navegador já logado: o cadastro abre a primeira sessão (ADR-0013)."""
    async with await _navegador(app) as navegador:
        assert (await navegador.post("/api/auth/cadastro", json=CADASTRO)).status_code == 201
        yield navegador


@pytest.fixture
async def outro_aparelho(app: FastAPI, maria: AsyncClient) -> AsyncIterator[AsyncClient]:
    """A mesma conta logada em outro navegador: uma segunda sessão."""
    async with await _navegador(app) as navegador:
        assert (await navegador.post("/api/auth/login", json=LOGIN)).status_code == 200
        yield navegador


def _hash_atual(usuarios: RepositorioUsuariosEmMemoria) -> str:
    return usuarios.credenciais[CADASTRO["email"]].senha_hash


# ─── POST /api/conta/senha ────────────────────────────────────────────────────────────────


async def test_trocar_senha_derruba_as_outras_sessoes_e_mantem_esta(
    app: FastAPI, maria: AsyncClient, outro_aparelho: AsyncClient
) -> None:
    resposta = await maria.post(
        "/api/conta/senha", json={"senha_atual": CADASTRO["senha"], "nova_senha": SENHA_NOVA}
    )

    assert resposta.status_code == 204
    assert (await maria.get("/api/auth/eu")).status_code == 200
    assert (await outro_aparelho.get("/api/auth/eu")).status_code == 401
    async with await _navegador(app) as novo:
        assert (await novo.post("/api/auth/login", json=LOGIN)).status_code == 401
        nova = {**LOGIN, "senha": SENHA_NOVA}
        assert (await novo.post("/api/auth/login", json=nova)).status_code == 200


async def test_senha_atual_errada_da_400_e_nada_muda(
    maria: AsyncClient,
    outro_aparelho: AsyncClient,
    usuarios: RepositorioUsuariosEmMemoria,
    sessoes: RepositorioSessoesEmMemoria,
) -> None:
    hash_antes = _hash_atual(usuarios)

    resposta = await maria.post(
        "/api/conta/senha", json={"senha_atual": "não é esta", "nova_senha": SENHA_NOVA}
    )

    assert resposta.status_code == 400
    assert resposta.json() == SENHA_ERRADA
    assert _hash_atual(usuarios) == hash_antes
    assert len(sessoes.sessoes) == 2
    assert (await outro_aparelho.get("/api/auth/eu")).status_code == 200


@pytest.mark.parametrize(
    ("nova_senha", "trecho"),
    [
        ("curta", "pelo menos 8 caracteres"),
        ("x" * 129, "no máximo 128 caracteres"),
        (CADASTRO["senha"], "diferente da atual"),
    ],
)
async def test_nova_senha_invalida_da_422_em_portugues(
    maria: AsyncClient, usuarios: RepositorioUsuariosEmMemoria, nova_senha: str, trecho: str
) -> None:
    hash_antes = _hash_atual(usuarios)

    resposta = await maria.post(
        "/api/conta/senha", json={"senha_atual": CADASTRO["senha"], "nova_senha": nova_senha}
    )

    assert resposta.status_code == 422
    assert trecho in resposta.json()["detail"]
    assert _hash_atual(usuarios) == hash_antes


class UsuariosLentos(RepositorioUsuariosEmMemoria):
    async def buscar_credenciais(self, email: str) -> CredenciaisArmazenadas | None:
        await asyncio.sleep(3600)
        raise AssertionError("o timeout deveria ter cortado antes")


@pytest.mark.parametrize(
    ("caminho", "corpo"),
    [
        ("/api/conta/senha", {"senha_atual": CADASTRO["senha"], "nova_senha": SENHA_NOVA}),
        ("/api/conta/excluir", {"senha": CADASTRO["senha"]}),
    ],
)
async def test_banco_lento_da_503_em_portugues(
    app: FastAPI,
    maria: AsyncClient,
    sessoes: RepositorioSessoesEmMemoria,
    caminho: str,
    corpo: dict[str, str],
) -> None:
    lentos = UsuariosLentos(sessoes)
    app.dependency_overrides[obter_repositorio_usuarios] = lambda: lentos
    app.dependency_overrides[get_settings] = lambda: settings_de_teste(timeout_autenticacao_s=0.05)

    resposta = await maria.post(caminho, json=corpo)

    assert resposta.status_code == 503
    assert resposta.json() == {
        "detail": "O serviço está iniciando. Tente de novo em alguns segundos."
    }


# ─── POST /api/conta/excluir ──────────────────────────────────────────────────────────────


async def test_excluir_com_a_senha_certa_apaga_a_conta_e_limpa_o_cookie(
    app: FastAPI,
    maria: AsyncClient,
    outro_aparelho: AsyncClient,
    usuarios: RepositorioUsuariosEmMemoria,
    sessoes: RepositorioSessoesEmMemoria,
) -> None:
    resposta = await maria.post("/api/conta/excluir", json={"senha": CADASTRO["senha"]})

    assert resposta.status_code == 204
    assert _atributos(_cookie_de_sessao(resposta))["max-age"] == "0"
    assert usuarios.credenciais == {}
    assert sessoes.sessoes == []
    assert (await outro_aparelho.get("/api/auth/eu")).status_code == 401
    async with await _navegador(app) as novo:
        assert (await novo.post("/api/auth/login", json=LOGIN)).status_code == 401


async def test_excluir_com_a_senha_errada_da_400_e_nada_some(
    maria: AsyncClient,
    usuarios: RepositorioUsuariosEmMemoria,
    sessoes: RepositorioSessoesEmMemoria,
) -> None:
    """Sessão aberta sozinha não basta: no celular da família, quem pega o aparelho não apaga a
    conta sem saber a senha (ADR-0019)."""
    resposta = await maria.post("/api/conta/excluir", json={"senha": "não é esta"})

    assert resposta.status_code == 400
    assert resposta.json() == SENHA_ERRADA
    assert "set-cookie" not in resposta.headers
    assert CADASTRO["email"] in usuarios.credenciais
    assert len(sessoes.sessoes) == 1
    assert (await maria.get("/api/auth/eu")).status_code == 200


# ─── sem sessão e OpenAPI ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("caminho", "corpo"),
    [
        ("/api/conta/senha", {"senha_atual": "x" * 8, "nova_senha": "y" * 8}),
        ("/api/conta/excluir", {"senha": "x" * 8}),
    ],
)
async def test_sem_sessao_da_401(app: FastAPI, caminho: str, corpo: dict[str, str]) -> None:
    async with await _navegador(app) as anonimo:
        resposta = await anonimo.post(caminho, json=corpo)

    assert resposta.status_code == 401
    assert resposta.json() == {"detail": "Você precisa entrar na sua conta."}


@pytest.mark.parametrize(
    ("caminho", "esperados"),
    [
        ("/api/conta/senha", {"400", "401", "422", "503"}),
        ("/api/conta/excluir", {"400", "401", "503"}),
    ],
)
def test_openapi_declara_os_erros_de_cada_rota(
    app: FastAPI, caminho: str, esperados: set[str]
) -> None:
    respostas = app.openapi()["paths"][caminho]["post"]["responses"]

    for codigo in esperados:
        assert codigo in respostas, f"POST {caminho} não declara {codigo}"
        assert "`detail`" in respostas[codigo]["description"]
