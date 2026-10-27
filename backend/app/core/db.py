"""Acesso ao PostgreSQL. Assíncrono de ponta a ponta (ADR-0001)."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def criar_engine(database_url: str) -> AsyncEngine:
    """Cria o engine. Não abre conexão aqui — o SQLAlchemy conecta sob demanda."""
    # pool_pre_ping descarta conexão morta antes de usá-la, o que acontece toda vez que o
    # container do Postgres reinicia com a aplicação no ar.
    # hide_parameters: o INSERT da análise logada carrega a mensagem (ADR-0018). Assim os valores
    # não vão para o log do SQLAlchemy nem para o texto de um `StatementError`.
    return create_async_engine(database_url, pool_pre_ping=True, hide_parameters=True)


def criar_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """`expire_on_commit=False`: sem isso, ler um atributo depois do commit dispara I/O."""
    return async_sessionmaker(engine, expire_on_commit=False)
