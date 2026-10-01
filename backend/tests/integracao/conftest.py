"""Fixtures dos testes de integração — os únicos que falam com um Postgres (CLAUDE.md §6).

Por que existem: o bug do ADR-0007 atravessou ruff, mypy, pytest e CI verdes porque só aparecia
contra um Postgres real. Estes testes rodam contra um banco **de teste** — o do docker compose ou
o serviço do CI — e nunca contra o Neon.

Como funcionam:
- A URL vem de TEST_DATABASE_URL (ambiente ou `.env`). Sem ela, tudo aqui é pulado — exceto no
  CI (CI=true), onde a coleta falha.
- O esquema vem do Alembic, nunca de `create_all`: a sessão faz `downgrade base` e `upgrade
  head`, então a migração é testada nos dois sentidos a cada execução.
- Cada teste roda dentro de uma transação que é desfeita no fim. O `commit()` do código vira um
  SAVEPOINT (`join_transaction_mode="create_savepoint"`, receita da documentação do SQLAlchemy
  2.0). Depois do rollback, uma conexão nova confere que nenhuma tabela ficou com linha.
"""

import asyncio
import os
import sys
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest
from alembic.config import Config
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from alembic import command
from app.core.config import normalizar_database_url
from app.models.base import Base

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


if sys.platform == "win32":
    # ADR-0007, terceiro lugar: o pytest-asyncio 1.4 cria ProactorEventLoop no Windows (medido),
    # e o psycopg async o recusa. Mesmo remédio do alembic/env.py — `loop_factory` explícito.
    # A política que `app.main` define ao ser importado não basta: ela só valia aqui por acidente,
    # porque o conftest raiz importa `app.main`. Este hook é o caminho que o pytest-asyncio
    # documenta (sobrescrever a fixture `event_loop_policy` está depreciado).
    def pytest_asyncio_loop_factories(
        config: pytest.Config, item: pytest.Item
    ) -> dict[str, Callable[[], asyncio.AbstractEventLoop]]:
        return {"selector": asyncio.SelectorEventLoop}


class _ConfigTeste(BaseSettings):
    """Lê só TEST_DATABASE_URL. Fica fora do `Settings` da aplicação: é coisa de teste."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    test_database_url: str | None = None


# Lida na carga deste conftest, que acontece na coleta de `tests/integracao`.
_URL_CONFIGURADA = _ConfigTeste().test_database_url

# No CI, faltar a variável é erro de configuração, não motivo para pular: um CI verde com os
# testes de banco pulados é o "verde sem testar" do ADR-0007. O GitHub Actions sempre define
# CI=true. Local, sem a variável, os testes só são pulados (ver fixture abaixo).
if not _URL_CONFIGURADA and os.environ.get("CI", "").lower() == "true":
    raise pytest.UsageError(
        "CI=true e TEST_DATABASE_URL ausente: no CI os testes de integração são obrigatórios. "
        "Defina TEST_DATABASE_URL no job, apontando para um banco que termine em '_teste'."
    )


def _validar_url_de_teste(url: str) -> str:
    """Duas travas contra apontar o teste para o banco errado.

    O `downgrade base` apaga o esquema inteiro: num banco que não é de teste, é perda de dado.
    """
    url = normalizar_database_url(url)
    partes = make_url(url)
    if (partes.host or "").endswith("neon.tech"):
        pytest.fail("TEST_DATABASE_URL aponta para o Neon. Teste nunca fala com produção.")
    if not (partes.database or "").endswith("_teste"):
        pytest.fail(
            f"O banco de teste precisa terminar em '_teste' (recebido: '{partes.database}'). "
            "A sessão de integração faz `downgrade base`, que apaga o esquema."
        )
    return url


def configurar_alembic(url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.attributes["database_url"] = url
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="session")
def url_banco_de_teste() -> str:
    """Prepara o esquema uma vez por sessão, pelo Alembic.

    Síncrona de propósito: o `env.py` chama `asyncio.run`, que não pode rodar dentro de um loop
    já ativo — e uma fixture async rodaria dentro do loop do pytest-asyncio.
    """
    url = _URL_CONFIGURADA
    if not url:
        pytest.skip(
            "TEST_DATABASE_URL não definida — testes de integração pulados. "
            "Ver README, seção 'Banco de teste'."
        )
    url = _validar_url_de_teste(url)
    config = configurar_alembic(url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    return url


@pytest.fixture
async def fabrica_de_sessoes(
    url_banco_de_teste: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Sessões presas a uma transação externa que é sempre desfeita.

    `NullPool` e engine por teste: cada teste do pytest-asyncio tem o próprio event loop, e uma
    conexão de pool aberta num loop não pode ser usada em outro.
    """
    engine = create_async_engine(url_banco_de_teste, poolclass=NullPool)
    try:
        async with engine.connect() as conexao:
            transacao = await conexao.begin()
            yield async_sessionmaker(
                bind=conexao,
                expire_on_commit=False,
                join_transaction_mode="create_savepoint",
            )
            await transacao.rollback()

        # Requisito "nenhum teste deixa linha para trás", conferido de fora da transação.
        async with engine.connect() as conexao:
            for tabela in Base.metadata.sorted_tables:
                linhas = await conexao.scalar(select(func.count()).select_from(tabela))
                assert linhas == 0, f"{tabela.name} ficou com {linhas} linha(s) depois do teste"
    finally:
        await engine.dispose()
