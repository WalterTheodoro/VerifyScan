"""/api/auth de ponta a ponta contra o Postgres real, com um cliente que guarda cookie.

A app usa os repositórios Postgres presos à transação do teste (conftest de integração). O
cliente fala https porque o cookie sai com Secure (default de produção) e o httpx não o devolve
em http.
"""

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import obter_repositorio_sessoes, obter_repositorio_usuarios
from app.core.config import get_settings
from app.main import criar_app
from app.models import SessaoUsuario, Usuario
from app.services.autenticacao import hash_do_token
from app.services.repositorio_sessoes import RepositorioSessoesPostgres
from app.services.repositorio_usuarios import RepositorioUsuariosPostgres
from tests.conftest import settings_de_teste

pytestmark = pytest.mark.integracao

CADASTRO = {"nome": "Maria", "email": "maria@exemplo.com", "senha": "uma senha boa"}
LOGIN = {"email": "maria@exemplo.com", "senha": "uma senha boa"}


@pytest.fixture
def app(fabrica_de_sessoes: async_sessionmaker[AsyncSession]) -> FastAPI:
    app = criar_app()
    app.dependency_overrides[obter_repositorio_usuarios] = lambda: RepositorioUsuariosPostgres(
        fabrica_de_sessoes
    )
    app.dependency_overrides[obter_repositorio_sessoes] = lambda: RepositorioSessoesPostgres(
        fabrica_de_sessoes
    )
    app.dependency_overrides[get_settings] = lambda: settings_de_teste()
    return app


@pytest.fixture
async def navegador(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://teste") as cliente:
        yield cliente


async def test_cadastro_eu_logout_eu(navegador: AsyncClient) -> None:
    cadastro = await navegador.post("/api/auth/cadastro", json=CADASTRO)
    assert cadastro.status_code == 201

    eu = await navegador.get("/api/auth/eu")
    assert eu.status_code == 200
    assert eu.json() == {"nome": "Maria", "email": "maria@exemplo.com"}

    assert (await navegador.post("/api/auth/logout")).status_code == 204
    assert (await navegador.get("/api/auth/eu")).status_code == 401


async def test_banco_guarda_hashes_e_nao_os_segredos(
    navegador: AsyncClient, fabrica_de_sessoes: async_sessionmaker[AsyncSession]
) -> None:
    await navegador.post("/api/auth/cadastro", json=CADASTRO)
    token = navegador.cookies["vs_sessao"]

    async with fabrica_de_sessoes() as sessao:
        usuario = await sessao.scalar(select(Usuario))
        token_hash = await sessao.scalar(select(SessaoUsuario.token_hash))

    assert usuario is not None
    assert usuario.senha_hash.startswith("$argon2id$")
    assert token_hash != token
    assert token_hash == hash_do_token(token)


async def test_login_errado_da_a_mesma_resposta_nos_dois_casos(navegador: AsyncClient) -> None:
    await navegador.post("/api/auth/cadastro", json=CADASTRO)
    navegador.cookies.clear()

    senha_errada = await navegador.post("/api/auth/login", json={**LOGIN, "senha": "errada!!"})
    inexistente = await navegador.post(
        "/api/auth/login", json={**LOGIN, "email": "ninguem@exemplo.com"}
    )

    assert senha_errada.status_code == inexistente.status_code == 401
    assert senha_errada.json() == inexistente.json() == {"detail": "E-mail ou senha incorretos."}

    certo = await navegador.post("/api/auth/login", json={**LOGIN, "email": " MARIA@exemplo.com"})
    assert certo.status_code == 200


async def test_email_duplicado_com_maiusculas_da_409(
    navegador: AsyncClient, fabrica_de_sessoes: async_sessionmaker[AsyncSession]
) -> None:
    await navegador.post("/api/auth/cadastro", json=CADASTRO)

    resposta = await navegador.post(
        "/api/auth/cadastro", json={**CADASTRO, "email": "Maria@Exemplo.COM"}
    )

    assert resposta.status_code == 409
    assert resposta.json() == {"detail": "Já existe uma conta com este e-mail."}
    async with fabrica_de_sessoes() as sessao:
        assert await sessao.scalar(select(func.count()).select_from(Usuario)) == 1


async def test_sessao_vencida_da_401(
    navegador: AsyncClient, fabrica_de_sessoes: async_sessionmaker[AsyncSession]
) -> None:
    await navegador.post("/api/auth/cadastro", json=CADASTRO)
    async with fabrica_de_sessoes() as sessao, sessao.begin():
        await sessao.execute(text("UPDATE sessoes SET expira_em = now() - interval '1 second'"))

    assert (await navegador.get("/api/auth/eu")).status_code == 401
