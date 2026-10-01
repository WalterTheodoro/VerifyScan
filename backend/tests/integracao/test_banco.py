"""O básico contra um Postgres real: o driver async conecta e o esquema está no head do Alembic."""

import asyncio
import sys

import pytest
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.integracao.conftest import configurar_alembic

pytestmark = pytest.mark.integracao


async def test_psycopg_async_roda_no_loop_do_pytest(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    """Guarda do ADR-0007: o psycopg async recusa o ProactorEventLoop do Windows."""
    if sys.platform == "win32":
        assert not isinstance(asyncio.get_running_loop(), asyncio.ProactorEventLoop)

    async with fabrica_de_sessoes() as sessao:
        assert await sessao.scalar(text("SELECT 1")) == 1


async def test_esquema_esta_no_head_do_alembic(
    url_banco_de_teste: str,
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    """O esquema de teste veio do Alembic, não de `create_all`."""
    head = ScriptDirectory.from_config(configurar_alembic(url_banco_de_teste)).get_current_head()

    def revisao_atual(conexao: Connection) -> str | None:
        return MigrationContext.configure(conexao).get_current_revision()

    async with fabrica_de_sessoes() as sessao:
        conexao = await sessao.connection()
        assert await conexao.run_sync(revisao_atual) == head
