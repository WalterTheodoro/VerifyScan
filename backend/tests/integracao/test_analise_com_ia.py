"""Análise com IA contra o Postgres real (migração 0005, ADR-0020).

Os CHECKs da 0005 são provados com SQL cru, sem ORM e sem Pydantic: quem recusa é o banco. O
caminho completo (análise → registro → histórico → desvinculação) usa a app com os repositórios
Postgres e o `ClienteIAFalso` — nenhuma chamada à Anthropic.
"""

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import (
    obter_analisador_ia,
    obter_repositorio_analises,
    obter_repositorio_historico,
    obter_repositorio_sessoes,
    obter_repositorio_usuarios,
)
from app.core.config import get_settings
from app.formulator.analisador import AnalisadorIA
from app.main import criar_app
from app.services.repositorio_analises import RepositorioAnalisesPostgres
from app.services.repositorio_historico import RepositorioHistoricoPostgres
from app.services.repositorio_sessoes import RepositorioSessoesPostgres
from app.services.repositorio_usuarios import RepositorioUsuariosPostgres
from tests.conftest import ClienteIAFalso, saida_da_ia, settings_de_teste
from tests.test_api_analise_com_ia import PENDENCIA_DOS_CORREIOS

pytestmark = pytest.mark.integracao

EXPLICACAO = {"tipo": "x", "sinais": [], "o_que_fazer": ["a", "b"]}


# ─── CHECKs da 0005 ───────────────────────────────────────────────────────────────────────


async def _inserir_usuario(sessao: AsyncSession) -> uuid.UUID:
    id_usuario = uuid.uuid4()
    await sessao.execute(
        text(
            "INSERT INTO usuarios (id, nome_exibicao, email, senha_hash) "
            "VALUES (:id, 'Maria', :email, 'x')"
        ),
        {"id": id_usuario, "email": f"{id_usuario}@exemplo.com"},
    )
    return id_usuario


async def _inserir_analise(sessao: AsyncSession, **colunas: object) -> None:
    valores: dict[str, object] = {
        "id": uuid.uuid4(),
        "score_risco": 0,
        "nivel_risco": "BAIXO",
        "tipo_input": "texto",
        "usuario_id": None,
        "nivel_motor": "BAIXO",
        "nivel_ia": None,
        "ia_modelo": None,
        "explicacao_ia": None,
        **colunas,
    }
    if valores["explicacao_ia"] is not None:
        valores["explicacao_ia"] = json.dumps(valores["explicacao_ia"])
    await sessao.execute(
        text(
            "INSERT INTO analises (id, score_risco, nivel_risco, tipo_input, usuario_id, "
            "nivel_motor, nivel_ia, ia_modelo, explicacao_ia) VALUES (:id, :score_risco, "
            ":nivel_risco, :tipo_input, :usuario_id, :nivel_motor, :nivel_ia, :ia_modelo, "
            "CAST(:explicacao_ia AS jsonb))"
        ),
        valores,
    )


@pytest.mark.parametrize(
    ("colunas", "constraint"),
    [
        ({"nivel_ia": "PERIGO", "ia_modelo": "m"}, "ck_analises_nivel_ia"),
        ({"nivel_ia": "BAIXO"}, "ck_analises_ia_com_modelo"),
        ({"ia_modelo": "m"}, "ck_analises_ia_com_modelo"),
    ],
    ids=["nivel-ia", "ia-sem-modelo", "modelo-sem-ia"],
)
async def test_banco_recusa_nivel_ou_modelo_fora_da_regra(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
    colunas: dict[str, object],
    constraint: str,
) -> None:
    async with fabrica_de_sessoes() as sessao:
        with pytest.raises(IntegrityError, match=constraint):
            await _inserir_analise(sessao, **colunas)


async def test_check_do_nivel_do_motor_existe(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    """Pelo catálogo, e não por um INSERT: um `nivel_motor` inválido viola também o
    `ck_analises_nivel_e_o_maior`, e o Postgres confere os CHECKs em ordem alfabética — o erro
    sempre citaria o outro."""
    async with fabrica_de_sessoes() as sessao:
        definicao = await sessao.scalar(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'ck_analises_nivel_motor'"
            )
        )

    assert definicao is not None
    for nivel in ("BAIXO", "MEDIO", "ALTO"):
        assert f"'{nivel}'" in definicao


@pytest.mark.parametrize(
    ("final", "motor", "ia", "aceita"),
    [
        ("MEDIO", "MEDIO", "BAIXO", True),
        ("BAIXO", "MEDIO", "BAIXO", False),
        ("ALTO", "BAIXO", "ALTO", True),
        ("MEDIO", "BAIXO", "ALTO", False),
        ("ALTO", "BAIXO", None, False),
        ("MEDIO", "MEDIO", None, True),
        ("ALTO", None, None, True),
    ],
    ids=[
        "ia-nao-baixa",
        "ia-baixou",
        "ia-subiu",
        "final-menor-que-a-ia",
        "subiu-sem-ia",
        "sem-ia",
        "linha-antiga",
    ],
)
async def test_banco_garante_que_o_final_e_o_maior(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
    final: str,
    motor: str | None,
    ia: str | None,
    aceita: bool,
) -> None:
    """A IA pode subir o nível, nunca baixar — garantido também pelo banco (ADR-0020)."""
    colunas = {
        "nivel_risco": final,
        "nivel_motor": motor,
        "nivel_ia": ia,
        "ia_modelo": "m" if ia else None,
    }
    async with fabrica_de_sessoes() as sessao:
        if aceita:
            await _inserir_analise(sessao, **colunas)
        else:
            with pytest.raises(IntegrityError, match="ck_analises_nivel_e_o_maior"):
                await _inserir_analise(sessao, **colunas)


async def test_banco_recusa_explicacao_sem_dono(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    """A explicação pode repetir trechos da mensagem: segue a regra do texto (ADR-0018)."""
    async with fabrica_de_sessoes() as sessao:
        with pytest.raises(IntegrityError, match="ck_analises_explicacao_so_com_dono"):
            await _inserir_analise(
                sessao, nivel_ia="BAIXO", ia_modelo="m", explicacao_ia=EXPLICACAO
            )


async def test_banco_recusa_explicacao_sem_o_nivel_da_ia(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    async with fabrica_de_sessoes() as sessao:
        with pytest.raises(IntegrityError, match="ck_analises_explicacao_com_ia"):
            await _inserir_analise(
                sessao, usuario_id=await _inserir_usuario(sessao), explicacao_ia=EXPLICACAO
            )


@pytest.mark.parametrize(("tamanho", "aceita"), [(3900, True), (4100, False)])
async def test_banco_limita_a_explicacao(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession], tamanho: int, aceita: bool
) -> None:
    explicacao = {"tipo": "x" * tamanho, "sinais": [], "o_que_fazer": ["a", "b"]}
    async with fabrica_de_sessoes() as sessao:
        colunas: dict[str, Any] = {
            "usuario_id": await _inserir_usuario(sessao),
            "nivel_ia": "BAIXO",
            "ia_modelo": "m",
            "explicacao_ia": explicacao,
        }
        if aceita:
            await _inserir_analise(sessao, **colunas)
        else:
            with pytest.raises(IntegrityError, match="ck_analises_explicacao_ate_4000"):
                await _inserir_analise(sessao, **colunas)


# ─── de ponta a ponta ─────────────────────────────────────────────────────────────────────


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
    app.dependency_overrides[obter_analisador_ia] = lambda: AnalisadorIA(
        ClienteIAFalso(saida_da_ia(nivel_sugerido="ALTO")), timeout_s=15
    )
    return app


@pytest.fixture
async def maria(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://teste") as cliente:
        resposta = await cliente.post(
            "/api/auth/cadastro",
            json={"nome": "Maria", "email": "maria@exemplo.com", "senha": "uma senha boa"},
        )
        assert resposta.status_code == 201
        yield cliente


@pytest.fixture
async def anonimo(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://teste") as cliente:
        yield cliente


async def _linhas(fabrica: async_sessionmaker[AsyncSession]) -> list[Any]:
    async with fabrica() as sessao:
        return list(
            (
                await sessao.execute(
                    text(
                        "SELECT usuario_id, nivel_risco, nivel_motor, nivel_ia, ia_modelo, "
                        "explicacao_ia, texto_input FROM analises"
                    )
                )
            ).all()
        )


async def test_logada_grava_niveis_e_explicacao_e_o_historico_mostra_igual(
    maria: AsyncClient, fabrica_de_sessoes: async_sessionmaker[AsyncSession]
) -> None:
    corpo = (await maria.post("/api/analises", json={"texto": PENDENCIA_DOS_CORREIOS})).json()

    [linha] = await _linhas(fabrica_de_sessoes)
    assert (linha.nivel_risco, linha.nivel_motor, linha.nivel_ia) == ("ALTO", "BAIXO", "ALTO")
    assert linha.ia_modelo == "claude-haiku-5-5"
    assert linha.explicacao_ia == corpo["explicacao_ia"]

    [item] = (await maria.get("/api/historico")).json()["analises"]
    assert item["nivel_risco"] == "ALTO"
    assert item["explicacao_ia"] == corpo["explicacao_ia"]
    assert item["orientacao"] == corpo["orientacao"]


async def test_anonima_grava_os_niveis_sem_explicacao(
    anonimo: AsyncClient, fabrica_de_sessoes: async_sessionmaker[AsyncSession]
) -> None:
    await anonimo.post("/api/analises", json={"texto": PENDENCIA_DOS_CORREIOS})

    [linha] = await _linhas(fabrica_de_sessoes)
    assert (linha.nivel_motor, linha.nivel_ia, linha.ia_modelo) == (
        "BAIXO",
        "ALTO",
        "claude-haiku-5-5",
    )
    assert linha.explicacao_ia is None
    assert linha.usuario_id is None


async def test_desvinculacao_zera_a_explicacao_e_guarda_os_niveis(
    maria: AsyncClient, fabrica_de_sessoes: async_sessionmaker[AsyncSession]
) -> None:
    """Os níveis ficam para medir quantas vezes a IA subiu; o conteúdo sai com o dono."""
    await maria.post("/api/analises", json={"texto": PENDENCIA_DOS_CORREIOS})
    async with fabrica_de_sessoes() as sessao, sessao.begin():
        await sessao.execute(text("UPDATE analises SET created_at = now() - interval '8 days'"))

    assert (await maria.get("/api/historico")).json()["analises"] == []

    [linha] = await _linhas(fabrica_de_sessoes)
    assert (linha.usuario_id, linha.texto_input, linha.explicacao_ia) == (None, None, None)
    assert (linha.nivel_risco, linha.nivel_motor, linha.nivel_ia) == ("ALTO", "BAIXO", "ALTO")


async def test_explicacao_descartada_grava_o_nivel_da_ia_sem_explicacao(
    app: FastAPI, maria: AsyncClient, fabrica_de_sessoes: async_sessionmaker[AsyncSession]
) -> None:
    """A IA deu ALTO e a explicação dela não cumpriu o mínimo: o nível vale no banco, com dono e
    sem explicação — o CHECK `explicacao_com_ia` aceita (ADR-0020, revisão da fatia 6)."""
    saida = saida_da_ia(nivel_sugerido="ALTO", o_que_fazer=["Pode confiar.", "Pague a taxa."])
    app.dependency_overrides[obter_analisador_ia] = lambda: AnalisadorIA(
        ClienteIAFalso(saida), timeout_s=15
    )

    corpo = (await maria.post("/api/analises", json={"texto": PENDENCIA_DOS_CORREIOS})).json()

    assert (corpo["nivel_risco"], corpo["explicacao_indisponivel"]) == ("ALTO", True)
    [linha] = await _linhas(fabrica_de_sessoes)
    assert (linha.nivel_risco, linha.nivel_motor, linha.nivel_ia) == ("ALTO", "BAIXO", "ALTO")
    assert linha.ia_modelo == "claude-haiku-5-5"
    assert linha.usuario_id is not None
    assert linha.explicacao_ia is None
