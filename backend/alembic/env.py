import asyncio
import sys
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import app.models  # noqa: F401 — registra as tabelas no metadata, para o autogenerate vê-las
from alembic import context
from app.core.config import get_settings, normalizar_database_url
from app.models.base import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config


def _url_do_banco() -> str:
    """De onde vem a URL, em ordem.

    1. `config.attributes["database_url"]`: quem chama o Alembic por código (os testes de
       integração) passa a URL do banco de teste por aqui, sem que o `.env` seja lido.
    2. `DATABASE_URL`, do ambiente ou do `.env`, pelo Settings — o caminho da linha de comando.

    Nunca do alembic.ini, que é versionado (invariante 7).
    """
    url_de_quem_chamou = config.attributes.get("database_url")
    if url_de_quem_chamou:
        return normalizar_database_url(url_de_quem_chamou)
    return get_settings().database_url


# O Config do Alembic interpola como o ConfigParser: um "%" cru na URL (senha com caractere
# codificado, "%40") quebraria a leitura. "%%" é o escape, e o get_section devolve o "%" de volta.
config.set_main_option("sqlalchemy.url", _url_do_banco().replace("%", "%%"))

# Interpret the config file for Python logging.
# This line sets up loggers basically.
# Quem chama por código pode recusar: o fileConfig desliga os loggers já existentes, e dentro do
# pytest isso calaria os logs da aplicação que os testes verificam (padrão do cookbook do Alembic).
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

# Metadata do projeto, usada pelo autogenerate e pelo `alembic check`. Só enxerga as tabelas
# cujos modelos foram importados — é para isso o `import app.models` acima.
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    # No Windows o event loop padrão do asyncio é o Proactor, e o psycopg em modo async se
    # recusa a rodar nele (psycopg.InterfaceError). O Selector é o que a própria mensagem de
    # erro do psycopg indica. O uvicorn resolve isso por conta própria; o alembic não.
    if sys.platform == "win32":
        asyncio.run(run_async_migrations(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
