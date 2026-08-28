"""Ponto de entrada da API.

uv run uvicorn app.main:app --port 8000 --loop none --reload
"""

import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as router_health
from app.core.cache import criar_redis
from app.core.config import get_settings
from app.core.db import criar_engine

# No Windows o event loop padrão do asyncio é o Proactor, e o psycopg em modo async se recusa a
# rodar nele. Trocar a política aqui, na importação do módulo, é o que faz qualquer processo que
# importe a aplicação nascer com o Selector — o mesmo guard do alembic/env.py.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Cria engine e cliente Redis uma vez por processo e fecha os dois na saída.

    Nenhum dos dois abre conexão aqui: ambos conectam sob demanda. Quem quiser saber se a
    infraestrutura responde deve chamar /health.
    """
    settings = get_settings()
    engine = criar_engine(settings.database_url)
    redis = criar_redis(settings.redis_url)
    app.state.engine = engine
    app.state.redis = redis
    try:
        yield
    finally:
        await redis.aclose()
        await engine.dispose()


def criar_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="VerifyScan",
        description="Análise de mensagens suspeitas: nível de risco, fatores e recomendação.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origens_cors,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router_health)
    return app


app = criar_app()
