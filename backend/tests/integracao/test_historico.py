"""Histórico de ponta a ponta contra o Postgres real (ADR-0015).

Duas contas, dois navegadores com cookie, a mesma app com os repositórios Postgres presos à
transação do teste. As datas são mudadas por SQL: dentro da transação o `now()` é fixo, então
"7 dias atrás" é exato — a borda da janela pode ser testada ao segundo.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import (
    obter_repositorio_analises,
    obter_repositorio_historico,
    obter_repositorio_sessoes,
    obter_repositorio_usuarios,
)
from app.core.config import get_settings
from app.main import criar_app
from app.models import Analise, IndicadorRisco, Usuario
from app.services.repositorio_analises import RepositorioAnalisesPostgres
from app.services.repositorio_historico import RepositorioHistoricoPostgres
from app.services.repositorio_sessoes import RepositorioSessoesPostgres
from app.services.repositorio_usuarios import RepositorioUsuariosPostgres, UsuarioAutenticado
from tests.conftest import settings_de_teste
from tests.test_api_analises import GOLPE_DE_PIX

pytestmark = pytest.mark.integracao

JANELA = "7 days"


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
    return app


@asynccontextmanager
async def _navegador_logado(app: FastAPI, nome: str) -> AsyncIterator[AsyncClient]:
    """Navegador com cookie, em https (o cookie é Secure), já logado numa conta nova."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://teste") as cliente:
        resposta = await cliente.post(
            "/api/auth/cadastro",
            json={"nome": nome, "email": f"{nome.lower()}@exemplo.com", "senha": "uma senha boa"},
        )
        assert resposta.status_code == 201
        yield cliente


@pytest.fixture
async def maria(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with _navegador_logado(app, "Maria") as navegador:
        yield navegador


@pytest.fixture
async def joao(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with _navegador_logado(app, "Joao") as navegador:
        yield navegador


@pytest.fixture
async def anonimo(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://teste") as cliente:
        yield cliente


async def _analisar(navegador: AsyncClient) -> dict[str, Any]:
    resposta = await navegador.post("/api/analises", json={"texto": GOLPE_DE_PIX})
    assert resposta.status_code == 200
    corpo: dict[str, Any] = resposta.json()
    return corpo


async def _id_da_conta(fabrica: async_sessionmaker[AsyncSession], nome: str) -> uuid.UUID:
    async with fabrica() as sessao:
        id_conta = await sessao.scalar(select(Usuario.id).where(Usuario.nome_exibicao == nome))
    assert id_conta is not None
    return id_conta


async def _donos(fabrica: async_sessionmaker[AsyncSession]) -> list[uuid.UUID | None]:
    async with fabrica() as sessao:
        return list((await sessao.scalars(select(Analise.usuario_id))).all())


async def _envelhecer(
    fabrica: async_sessionmaker[AsyncSession], idade_sql: str, dono: uuid.UUID | None = None
) -> None:
    """Põe `created_at = now() - <idade>` nas análises (de um dono, ou todas)."""
    filtro = "" if dono is None else " WHERE usuario_id = :dono"
    async with fabrica() as sessao, sessao.begin():
        await sessao.execute(
            text(f"UPDATE analises SET created_at = now() - interval '{idade_sql}'{filtro}"),
            {"dono": dono},
        )


# ─── registro com dono ────────────────────────────────────────────────────────────────────


async def test_com_cookie_grava_o_dono_e_sem_cookie_grava_null(
    maria: AsyncClient,
    anonimo: AsyncClient,
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    assert (await _analisar(maria))["salva_no_historico"] is True
    assert (await _analisar(anonimo))["salva_no_historico"] is False

    id_maria = await _id_da_conta(fabrica_de_sessoes, "Maria")
    assert sorted(await _donos(fabrica_de_sessoes), key=str) == sorted([id_maria, None], key=str)


class SessoesQueFalham(RepositorioSessoesPostgres):
    async def buscar_usuario(self, token_hash: str) -> UsuarioAutenticado | None:
        raise RuntimeError("consulta da sessão falhou")


async def test_falha_ao_consultar_a_sessao_grava_anonima(
    app: FastAPI,
    maria: AsyncClient,
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    app.dependency_overrides[obter_repositorio_sessoes] = lambda: SessoesQueFalham(
        fabrica_de_sessoes
    )

    corpo = await _analisar(maria)

    assert corpo["salva_no_historico"] is False
    assert await _donos(fabrica_de_sessoes) == [None]


# ─── listagem e janela ────────────────────────────────────────────────────────────────────


async def test_lista_so_as_da_conta_e_so_dentro_da_janela(
    maria: AsyncClient,
    joao: AsyncClient,
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    id_maria = await _id_da_conta(fabrica_de_sessoes, "Maria")
    await _analisar(maria)
    await _envelhecer(fabrica_de_sessoes, JANELA, id_maria)  # na borda: fica FORA
    await _analisar(maria)
    async with fabrica_de_sessoes() as sessao, sessao.begin():
        await sessao.execute(
            text(
                "UPDATE analises SET created_at = now() - interval '7 days' + interval '1 second' "
                "WHERE usuario_id = :dono AND created_at = now()"
            ),
            {"dono": id_maria},
        )
    recente = await _analisar(maria)
    await _analisar(joao)

    corpo = (await maria.get("/api/historico")).json()

    assert corpo["dias"] == 7
    assert len(corpo["analises"]) == 2
    # Mais recente primeiro: a de agora, depois a que está a 1 s de vencer.
    primeira, segunda = corpo["analises"]
    assert primeira["created_at"] > segunda["created_at"]
    assert primeira["score_risco"] == recente["score"]
    assert {f["categoria"] for f in primeira["fatores"]} == {
        f["categoria"] for f in recente["fatores"]
    }


async def test_desvinculacao_zera_so_as_antigas(
    app: FastAPI,
    maria: AsyncClient,
    joao: AsyncClient,
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    id_maria = await _id_da_conta(fabrica_de_sessoes, "Maria")
    id_joao = await _id_da_conta(fabrica_de_sessoes, "Joao")
    await _analisar(maria)
    await _envelhecer(fabrica_de_sessoes, "8 days", id_maria)
    await _analisar(maria)
    await _analisar(joao)

    # Listar é um dos dois gatilhos da desvinculação (o outro é a subida do processo).
    assert (await maria.get("/api/historico")).status_code == 200

    async with fabrica_de_sessoes() as sessao:
        linhas = (
            await sessao.execute(
                text(
                    "SELECT usuario_id, created_at < now() - interval '7 days' AS antiga "
                    "FROM analises"
                )
            )
        ).all()
    antigas = [linha.usuario_id for linha in linhas if linha.antiga]
    recentes = sorted((linha.usuario_id for linha in linhas if not linha.antiga), key=str)
    assert antigas == [None]
    assert recentes == sorted([id_maria, id_joao], key=str)
    # Desvinculada não é apagada: vira idêntica a uma anônima (ADR-0006), com os indicadores.
    async with fabrica_de_sessoes() as sessao:
        assert await sessao.scalar(select(func.count()).select_from(Analise)) == 3


async def test_desvinculacao_direta_pelo_repositorio(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
    maria: AsyncClient,
    joao: AsyncClient,
) -> None:
    id_joao = await _id_da_conta(fabrica_de_sessoes, "Joao")
    await _analisar(maria)
    await _analisar(joao)
    await _envelhecer(fabrica_de_sessoes, "7 days", id_joao)

    desvinculadas = await RepositorioHistoricoPostgres(fabrica_de_sessoes).desvincular_vencidas(
        timedelta(days=7)
    )

    assert desvinculadas == 1
    assert None in await _donos(fabrica_de_sessoes)


# ─── apagar ───────────────────────────────────────────────────────────────────────────────


async def _contar(fabrica: async_sessionmaker[AsyncSession]) -> tuple[int, int]:
    async with fabrica() as sessao:
        analises = await sessao.scalar(select(func.count()).select_from(Analise)) or 0
        indicadores = await sessao.scalar(select(func.count()).select_from(IndicadorRisco)) or 0
    return analises, indicadores


async def test_dona_apaga_uma_e_outra_pessoa_recebe_404(
    maria: AsyncClient,
    joao: AsyncClient,
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    await _analisar(maria)
    id_analise = (await maria.get("/api/historico")).json()["analises"][0]["id"]
    _, indicadores = await _contar(fabrica_de_sessoes)
    assert indicadores > 0

    tentativa = await joao.delete(f"/api/historico/{id_analise}")
    assert tentativa.status_code == 404
    assert await _contar(fabrica_de_sessoes) == (1, indicadores)

    assert (await maria.delete(f"/api/historico/{id_analise}")).status_code == 204
    assert await _contar(fabrica_de_sessoes) == (0, 0)


async def test_apagar_todas_so_apaga_as_da_conta(
    maria: AsyncClient,
    joao: AsyncClient,
    anonimo: AsyncClient,
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    id_joao = await _id_da_conta(fabrica_de_sessoes, "Joao")
    await _analisar(maria)
    await _analisar(maria)
    await _analisar(joao)
    await _analisar(anonimo)

    assert (await maria.delete("/api/historico")).status_code == 204

    assert sorted(await _donos(fabrica_de_sessoes), key=str) == sorted([id_joao, None], key=str)


async def test_apagar_a_conta_apaga_as_analises_vinculadas(
    maria: AsyncClient,
    anonimo: AsyncClient,
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    await _analisar(maria)
    await _analisar(anonimo)
    _, indicadores_antes = await _contar(fabrica_de_sessoes)

    async with fabrica_de_sessoes() as sessao, sessao.begin():
        # SQL cru, sem ORM: quem apaga é o ON DELETE CASCADE da 0003 (e o da 0001, nos filhos).
        await sessao.execute(text("DELETE FROM usuarios WHERE nome_exibicao = 'Maria'"))

    assert await _donos(fabrica_de_sessoes) == [None]
    analises, indicadores = await _contar(fabrica_de_sessoes)
    assert analises == 1
    assert indicadores == indicadores_antes // 2


# ─── conta e sem sessão ───────────────────────────────────────────────────────────────────


async def test_conta_devolve_os_dados_da_propria_conta(
    maria: AsyncClient, joao: AsyncClient
) -> None:
    corpo = (await maria.get("/api/conta")).json()

    assert corpo["nome"] == "Maria"
    assert corpo["email"] == "maria@exemplo.com"
    assert corpo["criado_em"]


@pytest.mark.parametrize(
    ("metodo", "caminho"),
    [
        ("GET", "/api/historico"),
        ("DELETE", f"/api/historico/{uuid.uuid4()}"),
        ("DELETE", "/api/historico"),
        ("GET", "/api/conta"),
    ],
)
async def test_sem_sessao_as_quatro_rotas_dao_401(
    anonimo: AsyncClient, metodo: str, caminho: str
) -> None:
    assert (await anonimo.request(metodo, caminho)).status_code == 401
