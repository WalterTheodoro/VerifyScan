"""Os CHECKs do esquema existem no banco — um caso por CHECK.

Este teste existe porque o autogenerate do Alembic não compara CHECK constraint: se o modelo e a
migração divergirem num CHECK, o `alembic check` do CI fica verde. O insert é SQL cru, sem ORM e
sem Pydantic, para provar que quem recusa é o banco.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integracao

ANALISE_VALIDA = {"score_risco": 0, "nivel_risco": "BAIXO", "tipo_input": "texto"}
INDICADOR_VALIDO = {"tipo": "texto", "categoria": "urgencia", "descricao": "x", "peso": 10}


@pytest.mark.parametrize(
    ("tabela", "coluna", "valor_invalido", "constraint"),
    [
        ("analises", "nivel_risco", "MÉDIO", "ck_analises_nivel_risco"),
        # `imagem` passou a valer na 0006 (ADR-0023).
        ("analises", "tipo_input", "audio", "ck_analises_tipo_input"),
        ("indicadores_risco", "tipo", "url", "ck_indicadores_risco_tipo"),
        ("indicadores_risco", "peso", 0, "ck_indicadores_risco_peso_positivo"),
    ],
)
async def test_banco_recusa_valor_fora_do_check(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
    tabela: str,
    coluna: str,
    valor_invalido: object,
    constraint: str,
) -> None:
    id_analise = uuid.uuid4()
    analise = {"id": id_analise, **ANALISE_VALIDA}
    indicador = {"id": uuid.uuid4(), "analise_id": id_analise, **INDICADOR_VALIDO}

    async with fabrica_de_sessoes() as sessao:
        if tabela == "analises":
            analise[coluna] = valor_invalido
        else:
            await _inserir(sessao, "analises", analise)
            indicador[coluna] = valor_invalido

        with pytest.raises(IntegrityError, match=constraint):
            await _inserir(sessao, tabela, analise if tabela == "analises" else indicador)


async def _inserir(sessao: AsyncSession, tabela: str, valores: dict[str, object]) -> None:
    colunas = ", ".join(valores)
    parametros = ", ".join(f":{coluna}" for coluna in valores)
    await sessao.execute(text(f"INSERT INTO {tabela} ({colunas}) VALUES ({parametros})"), valores)


# ─── texto da mensagem (migração 0004, ADR-0018) ──────────────────────────────────────────


async def _inserir_usuario(sessao: AsyncSession) -> uuid.UUID:
    id_usuario = uuid.uuid4()
    await _inserir(
        sessao,
        "usuarios",
        {
            "id": id_usuario,
            "nome_exibicao": "Maria",
            "email": f"{id_usuario}@exemplo.com",
            "senha_hash": "x",
        },
    )
    return id_usuario


async def test_banco_recusa_texto_em_analise_sem_dono(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    """ADR-0006 continua valendo no banco: análise anônima nunca tem texto."""
    async with fabrica_de_sessoes() as sessao:
        with pytest.raises(IntegrityError, match="ck_analises_texto_so_com_dono"):
            await _inserir(
                sessao,
                "analises",
                {"id": uuid.uuid4(), **ANALISE_VALIDA, "texto_input": "mensagem"},
            )


@pytest.mark.parametrize(("tamanho", "aceita"), [(5000, True), (5001, False)])
async def test_banco_limita_o_texto_a_5000_caracteres(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession], tamanho: int, aceita: bool
) -> None:
    """`char_length` conta caracteres, como o `len` do Python que valida a entrada: "ç" é um só."""
    async with fabrica_de_sessoes() as sessao:
        analise = {
            "id": uuid.uuid4(),
            **ANALISE_VALIDA,
            "usuario_id": await _inserir_usuario(sessao),
            "texto_input": "ç" * tamanho,
        }
        if aceita:
            await _inserir(sessao, "analises", analise)
        else:
            with pytest.raises(IntegrityError, match="ck_analises_texto_ate_5000"):
                await _inserir(sessao, "analises", analise)
