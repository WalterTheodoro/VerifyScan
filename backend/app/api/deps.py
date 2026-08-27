"""Dependências das rotas.

Cada `obter_*` é o ponto de substituição usado pelos testes via `dependency_overrides`.
Engine e cliente Redis vêm de `app.state`, onde o `lifespan` os deixou.
"""

from fastapi import Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import get_settings
from app.services.health import VerificadorPostgres, VerificadorRedis, VerificadorSaude


def obter_verificador_postgres(request: Request) -> VerificadorSaude:
    engine: AsyncEngine = request.app.state.engine
    return VerificadorPostgres(engine, get_settings().timeout_health_s)


def obter_verificador_redis(request: Request) -> VerificadorSaude:
    redis: Redis = request.app.state.redis
    return VerificadorRedis(redis, get_settings().timeout_health_s)
