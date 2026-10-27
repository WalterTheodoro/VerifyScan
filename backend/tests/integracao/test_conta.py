"""Trocar senha, excluir a conta e a faxina das sessões contra o Postgres real (ADR-0019).

Duas contas e três navegadores com cookie: Maria em dois aparelhos e João. As contagens são feitas
por SQL, de fora da API: quem prova que a exclusão não deixa nada para trás é o banco.
"""

import uuid
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import (
    obter_analisador_ia,
    obter_repositorio_analises,
    obter_repositorio_historico,
    obter_repositorio_sessoes,
    obter_repositorio_usuarios,
)
from app.core.config import get_settings
from app.main import criar_app
from app.models import SessaoUsuario, Usuario
from app.services.autenticacao import hash_do_token
from app.services.repositorio_analises import RepositorioAnalisesPostgres
from app.services.repositorio_historico import RepositorioHistoricoPostgres
from app.services.repositorio_sessoes import RepositorioSessoesPostgres
from app.services.repositorio_usuarios import RepositorioUsuariosPostgres
from tests.conftest import ia_desligada, settings_de_teste
from tests.test_api_analises import GOLPE_DE_PIX

pytestmark = pytest.mark.integracao

SENHA = "uma senha boa"
SENHA_NOVA = "outra senha boa"


@pytest.fixture
def app(fabrica_de_sessoes: async_sessionmaker[AsyncSession]) -> FastAPI:
    app = criar_app()
    app.dependency_overrides[obter_repositorio_analises] = lambda: RepositorioAnalisesPostgres(
        fabrica_de_sessoes
    )
    app.dependency_overrides[obter_repositorio_usuarios] = lambda: RepositorioUsuariosPostgres(
        fabrica_de_sessoes
    )
    app.dependency_overrides[obter_repositorio_sessoes] = lambda: RepositorioSessoesPostgres(
        fabrica_de_sessoes
    )
    app.dependency_overrides[obter_repositorio_historico] = lambda: RepositorioHistoricoPostgres(
        fabrica_de_sessoes
    )
    app.dependency_overrides[get_settings] = lambda: settings_de_teste()
    app.dependency_overrides[obter_analisador_ia] = ia_desligada
    return app


def _navegador(app: FastAPI) -> AsyncClient:
    """Em https: o cookie sai com Secure, e o httpx não o devolve em http."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="https://teste")


def _login(nome: str, senha: str = SENHA) -> dict[str, str]:
    return {"email": f"{nome.lower()}@exemplo.com", "senha": senha}


@pytest.fixture
async def maria(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with _navegador(app) as navegador:
        cadastro = {"nome": "Maria", **_login("Maria")}
        assert (await navegador.post("/api/auth/cadastro", json=cadastro)).status_code == 201
        yield navegador


@pytest.fixture
async def maria_no_celular(app: FastAPI, maria: AsyncClient) -> AsyncIterator[AsyncClient]:
    async with _navegador(app) as navegador:
        assert (await navegador.post("/api/auth/login", json=_login("Maria"))).status_code == 200
        yield navegador


@pytest.fixture
async def joao(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with _navegador(app) as navegador:
        cadastro = {"nome": "Joao", **_login("Joao")}
        assert (await navegador.post("/api/auth/cadastro", json=cadastro)).status_code == 201
        yield navegador


async def _analisar(navegador: AsyncClient) -> None:
    resposta = await navegador.post("/api/analises", json={"texto": GOLPE_DE_PIX})
    assert resposta.json()["texto_salvo"] is True


async def _estado_da_conta(
    fabrica: async_sessionmaker[AsyncSession], nome: str
) -> tuple[str | None, int]:
    """Hash da senha e número de sessões da conta, lidos direto do banco."""
    async with fabrica() as sessao:
        senha_hash = await sessao.scalar(
            select(Usuario.senha_hash).where(Usuario.nome_exibicao == nome)
        )
        sessoes = (
            await sessao.scalars(
                select(SessaoUsuario.id)
                .join(Usuario, Usuario.id == SessaoUsuario.usuario_id)
                .where(Usuario.nome_exibicao == nome)
            )
        ).all()
    return senha_hash, len(sessoes)


# ─── trocar senha ─────────────────────────────────────────────────────────────────────────


async def test_trocar_senha_com_a_atual_errada_da_400_e_nada_muda(
    maria: AsyncClient,
    maria_no_celular: AsyncClient,
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    antes = await _estado_da_conta(fabrica_de_sessoes, "Maria")

    resposta = await maria.post(
        "/api/conta/senha", json={"senha_atual": "não é esta", "nova_senha": SENHA_NOVA}
    )

    assert resposta.status_code == 400
    assert resposta.json() == {"detail": "A senha atual não confere."}
    assert await _estado_da_conta(fabrica_de_sessoes, "Maria") == antes
    assert antes[1] == 2


async def test_trocar_senha_grava_o_hash_novo_e_derruba_so_as_outras_sessoes(
    app: FastAPI,
    maria: AsyncClient,
    maria_no_celular: AsyncClient,
    joao: AsyncClient,
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    hash_antes, _ = await _estado_da_conta(fabrica_de_sessoes, "Maria")

    resposta = await maria.post(
        "/api/conta/senha", json={"senha_atual": SENHA, "nova_senha": SENHA_NOVA}
    )

    assert resposta.status_code == 204
    hash_depois, sessoes = await _estado_da_conta(fabrica_de_sessoes, "Maria")
    assert hash_depois != hash_antes
    assert hash_depois is not None and hash_depois.startswith("$argon2id$")
    assert sessoes == 1
    assert (await maria.get("/api/auth/eu")).status_code == 200
    assert (await maria_no_celular.get("/api/auth/eu")).status_code == 401
    # As sessões de outra conta não entram na troca.
    assert (await joao.get("/api/auth/eu")).status_code == 200
    async with _navegador(app) as novo:
        assert (await novo.post("/api/auth/login", json=_login("Maria"))).status_code == 401
        resposta = await novo.post("/api/auth/login", json=_login("Maria", SENHA_NOVA))
        assert resposta.status_code == 200


# ─── excluir a conta ──────────────────────────────────────────────────────────────────────


async def _contagens(fabrica: async_sessionmaker[AsyncSession], nome: str) -> dict[str, int]:
    """Linhas ligadas à conta em cada tabela. Os indicadores são contados pela análise do dono."""
    consultas = {
        "usuarios": "SELECT count(*) FROM usuarios WHERE nome_exibicao = :nome",
        "sessoes": "SELECT count(*) FROM sessoes s JOIN usuarios u ON u.id = s.usuario_id "
        "WHERE u.nome_exibicao = :nome",
        "analises": "SELECT count(*) FROM analises a JOIN usuarios u ON u.id = a.usuario_id "
        "WHERE u.nome_exibicao = :nome",
        "indicadores": "SELECT count(*) FROM indicadores_risco i "
        "JOIN analises a ON a.id = i.analise_id JOIN usuarios u ON u.id = a.usuario_id "
        "WHERE u.nome_exibicao = :nome",
    }
    async with fabrica() as sessao:
        return {
            tabela: (await sessao.scalar(text(sql), {"nome": nome})) or 0
            for tabela, sql in consultas.items()
        }


async def _total(fabrica: async_sessionmaker[AsyncSession], tabela: str) -> int:
    async with fabrica() as sessao:
        return (await sessao.scalar(text(f"SELECT count(*) FROM {tabela}"))) or 0


async def test_excluir_com_a_senha_errada_da_400_e_nada_some(
    maria: AsyncClient,
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    await _analisar(maria)
    antes = await _contagens(fabrica_de_sessoes, "Maria")

    resposta = await maria.post("/api/conta/excluir", json={"senha": "não é esta"})

    assert resposta.status_code == 400
    assert resposta.json() == {"detail": "A senha não confere."}
    assert await _contagens(fabrica_de_sessoes, "Maria") == antes
    assert antes["usuarios"] == antes["sessoes"] == antes["analises"] == 1
    assert antes["indicadores"] > 0


async def test_excluir_apaga_tudo_da_conta_e_nada_da_outra(
    maria: AsyncClient,
    maria_no_celular: AsyncClient,
    joao: AsyncClient,
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    await _analisar(maria)
    await _analisar(joao)
    do_joao = await _contagens(fabrica_de_sessoes, "Joao")
    id_maria = await _id(fabrica_de_sessoes, "Maria")
    # Pré-condição explícita: a análise da Maria tem texto. Se a FK fosse SET NULL, este DELETE
    # violaria `ck_analises_texto_so_com_dono`; com CASCADE, a linha inteira sai junto.
    async with fabrica_de_sessoes() as sessao:
        texto = await sessao.scalar(
            text("SELECT texto_input FROM analises WHERE usuario_id = :id"), {"id": id_maria}
        )
    assert texto == GOLPE_DE_PIX

    resposta = await maria.post("/api/conta/excluir", json={"senha": SENHA})

    assert resposta.status_code == 204
    cookie = resposta.headers["set-cookie"]
    assert cookie.startswith("vs_sessao=") and "Max-Age=0" in cookie
    assert await _contagens(fabrica_de_sessoes, "Maria") == {
        "usuarios": 0,
        "sessoes": 0,
        "analises": 0,
        "indicadores": 0,
    }
    # Por id também: nenhuma linha órfã ficou apontando para a conta apagada.
    async with fabrica_de_sessoes() as sessao:
        for tabela in ("sessoes", "analises"):
            orfas = await sessao.scalar(
                text(f"SELECT count(*) FROM {tabela} WHERE usuario_id = :id"), {"id": id_maria}
            )
            assert orfas == 0, tabela
    assert await _contagens(fabrica_de_sessoes, "Joao") == do_joao
    assert await _total(fabrica_de_sessoes, "indicadores_risco") == do_joao["indicadores"]
    assert (await maria_no_celular.get("/api/auth/eu")).status_code == 401
    assert (await joao.get("/api/auth/eu")).status_code == 200


async def _id(fabrica: async_sessionmaker[AsyncSession], nome: str) -> uuid.UUID:
    async with fabrica() as sessao:
        id_conta = await sessao.scalar(select(Usuario.id).where(Usuario.nome_exibicao == nome))
    assert id_conta is not None
    return id_conta


# ─── faxina das sessões vencidas ──────────────────────────────────────────────────────────


async def test_faxina_apaga_as_sessoes_vencidas_e_deixa_as_validas(
    maria: AsyncClient,
    maria_no_celular: AsyncClient,
    joao: AsyncClient,
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    """O achado de 26/10: vencidas de quem não volta ficavam no banco. Agora qualquer listagem
    as apaga, de todas as contas."""
    id_joao = await _id(fabrica_de_sessoes, "Joao")
    async with fabrica_de_sessoes() as sessao, sessao.begin():
        # A sessão do João vence; a do celular da Maria vence exatamente agora (`<= now()`).
        await sessao.execute(
            text("UPDATE sessoes SET expira_em = now() - interval '1 day' WHERE usuario_id = :id"),
            {"id": id_joao},
        )
        await sessao.execute(
            text("UPDATE sessoes SET expira_em = now() WHERE token_hash = :hash"),
            {"hash": hash_do_token(maria_no_celular.cookies["vs_sessao"])},
        )
    assert await _total(fabrica_de_sessoes, "sessoes") == 3

    assert (await maria.get("/api/historico")).status_code == 200

    assert await _total(fabrica_de_sessoes, "sessoes") == 1
    assert (await maria.get("/api/auth/eu")).status_code == 200
    assert (await maria_no_celular.get("/api/auth/eu")).status_code == 401
