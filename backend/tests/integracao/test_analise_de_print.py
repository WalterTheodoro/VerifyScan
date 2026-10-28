"""Análise de print contra o Postgres real (migração 0006, ADR-0023).

Os CHECKs da 0006 com SQL cru, sem ORM e sem Pydantic: quem recusa é o banco. O caminho completo
(print → leitura falsa → registro → histórico → desvinculação) usa a app com os repositórios
Postgres e os clientes falsos de leitura e de análise — nenhuma chamada à Anthropic.
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
    obter_leitor_de_print,
    obter_repositorio_analises,
    obter_repositorio_historico,
    obter_repositorio_sessoes,
    obter_repositorio_usuarios,
)
from app.core.config import get_settings
from app.formulator.analisador import AnalisadorIA
from app.main import criar_app
from app.ocr.leitura import LeitorDePrint
from app.services.repositorio_analises import RepositorioAnalisesPostgres
from app.services.repositorio_historico import RepositorioHistoricoPostgres
from app.services.repositorio_sessoes import RepositorioSessoesPostgres
from app.services.repositorio_usuarios import RepositorioUsuariosPostgres
from tests.conftest import (
    ClienteIAFalso,
    ClienteLeituraFalso,
    corpo_de_print,
    saida_da_ia,
    saida_da_leitura,
    settings_de_teste,
)

pytestmark = pytest.mark.integracao

CONTEXTO = {
    "canal": "sms",
    "remetente_salvo": "nao",
    "aviso_do_app": "sim",
    "primeira_mensagem": "sim",
    "tem_link_visivel": "sim",
}
CONVERSA = [
    ("pessoa", "Quem é? Veja meu site www.site-da-pessoa.example"),
    ("contato", "Sua entrega está retida. Pague a taxa em http://correios-taxa.example/pagar"),
]


# ─── CHECKs da 0006 ───────────────────────────────────────────────────────────────────────


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
        "tipo_input": "imagem",
        "usuario_id": None,
        "nivel_motor": "BAIXO",
        "texto_input": None,
        "contexto_print": None,
        **colunas,
    }
    if valores["contexto_print"] is not None:
        valores["contexto_print"] = json.dumps(valores["contexto_print"])
    await sessao.execute(
        text(
            "INSERT INTO analises (id, score_risco, nivel_risco, tipo_input, usuario_id, "
            "nivel_motor, texto_input, contexto_print) VALUES (:id, :score_risco, :nivel_risco, "
            ":tipo_input, :usuario_id, :nivel_motor, :texto_input, "
            "CAST(:contexto_print AS jsonb))"
        ),
        valores,
    )


async def test_banco_aceita_analise_de_imagem_anonima_sem_conteudo(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    async with fabrica_de_sessoes() as sessao:
        await _inserir_analise(sessao)


async def test_banco_aceita_imagem_com_dono_transcricao_e_contexto(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    async with fabrica_de_sessoes() as sessao:
        await _inserir_analise(
            sessao,
            usuario_id=await _inserir_usuario(sessao),
            texto_input="[recebida]\noi",
            contexto_print=CONTEXTO,
        )


async def test_banco_ainda_recusa_tipo_desconhecido(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    async with fabrica_de_sessoes() as sessao:
        with pytest.raises(IntegrityError, match="ck_analises_tipo_input"):
            await _inserir_analise(sessao, tipo_input="audio")


async def test_banco_recusa_contexto_sem_dono(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    async with fabrica_de_sessoes() as sessao:
        with pytest.raises(IntegrityError, match="ck_analises_contexto_print_so_com_dono"):
            await _inserir_analise(sessao, contexto_print=CONTEXTO)


async def test_banco_recusa_contexto_em_analise_de_texto(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    async with fabrica_de_sessoes() as sessao:
        with pytest.raises(IntegrityError, match="ck_analises_contexto_print_so_de_imagem"):
            await _inserir_analise(
                sessao,
                tipo_input="texto",
                usuario_id=await _inserir_usuario(sessao),
                contexto_print=CONTEXTO,
            )


async def test_banco_limita_o_tamanho_do_contexto(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    async with fabrica_de_sessoes() as sessao:
        with pytest.raises(IntegrityError, match="ck_analises_contexto_print_ate_500"):
            await _inserir_analise(
                sessao,
                usuario_id=await _inserir_usuario(sessao),
                contexto_print={**CONTEXTO, "extra": "x" * 500},
            )


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
    app.dependency_overrides[obter_leitor_de_print] = lambda: LeitorDePrint(
        ClienteLeituraFalso(saida_da_leitura(CONVERSA, **CONTEXTO)), timeout_s=10
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
                        "SELECT usuario_id, tipo_input, texto_input, contexto_print, "
                        "explicacao_ia, nivel_risco FROM analises"
                    )
                )
            ).all()
        )


async def test_logada_grava_a_transcricao_marcada_e_o_contexto(
    maria: AsyncClient, fabrica_de_sessoes: async_sessionmaker[AsyncSession]
) -> None:
    resposta = await maria.post("/api/analises/imagem", json=corpo_de_print(texto="Recebi hoje"))
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["texto_salvo"] is True

    [linha] = await _linhas(fabrica_de_sessoes)
    assert linha.tipo_input == "imagem"
    assert linha.usuario_id is not None
    # Todas as mensagens, com quem mandou; o texto digitado também.
    assert linha.texto_input == (
        "[enviada pela pessoa]\nQuem é? Veja meu site www.site-da-pessoa.example\n\n"
        "[recebida]\nSua entrega está retida. Pague a taxa em "
        "http://correios-taxa.example/pagar\n\n"
        "[a pessoa também escreveu]\nRecebi hoje"
    )
    assert linha.contexto_print == CONTEXTO


async def test_historico_mostra_o_print_e_os_links_so_do_que_foi_recebido(
    maria: AsyncClient,
) -> None:
    await maria.post("/api/analises/imagem", json=corpo_de_print())

    [item] = (await maria.get("/api/historico")).json()["analises"]
    assert item["tipo_input"] == "imagem"
    assert item["contexto_print"] == CONTEXTO
    assert "[enviada pela pessoa]" in item["texto"]
    assert [link["dominio"] for link in item["links"]] == ["correios-taxa.example"]
    # Guardado inteiro; na tela, só o domínio (correção 9.1).
    assert "http://correios-taxa.example/pagar" in item["texto"]
    assert item["texto_para_exibir"] == (
        "[enviada pela pessoa]\nQuem é? Veja meu site [link: site-da-pessoa.example]\n\n"
        "[recebida]\nSua entrega está retida. Pague a taxa em [link: correios-taxa.example]"
    )


async def test_anonima_nao_grava_transcricao_nem_contexto(
    anonimo: AsyncClient, fabrica_de_sessoes: async_sessionmaker[AsyncSession]
) -> None:
    resposta = await anonimo.post("/api/analises/imagem", json=corpo_de_print())
    assert resposta.status_code == 200
    assert resposta.json()["leitura_do_print"]["contexto"] == CONTEXTO

    [linha] = await _linhas(fabrica_de_sessoes)
    assert (linha.usuario_id, linha.texto_input, linha.contexto_print) == (None, None, None)
    assert linha.tipo_input == "imagem"


async def test_desvinculacao_zera_transcricao_explicacao_e_contexto(
    maria: AsyncClient, fabrica_de_sessoes: async_sessionmaker[AsyncSession]
) -> None:
    await maria.post("/api/analises/imagem", json=corpo_de_print())
    async with fabrica_de_sessoes() as sessao, sessao.begin():
        await sessao.execute(text("UPDATE analises SET created_at = now() - interval '8 days'"))

    assert (await maria.get("/api/historico")).json()["analises"] == []

    [linha] = await _linhas(fabrica_de_sessoes)
    assert (linha.usuario_id, linha.texto_input, linha.explicacao_ia, linha.contexto_print) == (
        None,
        None,
        None,
        None,
    )
    assert (linha.tipo_input, linha.nivel_risco) == ("imagem", "ALTO")


async def test_leitura_que_falha_nao_grava_nada(
    app: FastAPI, maria: AsyncClient, fabrica_de_sessoes: async_sessionmaker[AsyncSession]
) -> None:
    app.dependency_overrides[obter_leitor_de_print] = lambda: LeitorDePrint(
        ClienteLeituraFalso(saida_da_leitura(legivel="nao")), timeout_s=10
    )
    resposta = await maria.post("/api/analises/imagem", json=corpo_de_print())

    assert resposta.status_code == 422
    assert await _linhas(fabrica_de_sessoes) == []
