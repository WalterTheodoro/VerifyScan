"""Dependências das rotas.

Cada `obter_*` é o ponto de substituição usado pelos testes via `dependency_overrides`.
Engine, fábrica de sessões e cliente Redis vêm de `app.state`, onde o `lifespan` os deixou.
"""

from functools import lru_cache

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.analyzers.texto import TextAnalyzer
from app.analyzers.urls import URLExtractor
from app.core.config import get_settings
from app.scoring.motor import ScoringEngine
from app.scoring.regras import carregar_regras
from app.services.analise import ServicoAnalise
from app.services.health import (
    VerificadorDesativado,
    VerificadorPostgres,
    VerificadorRedis,
    VerificadorSaude,
)
from app.services.orquestrador import OrquestradorAnalise
from app.services.repositorio_analises import RepositorioAnalises, RepositorioAnalisesPostgres


def obter_verificador_postgres(request: Request) -> VerificadorSaude:
    engine: AsyncEngine = request.app.state.engine
    return VerificadorPostgres(engine, get_settings().timeout_health_s)


def obter_verificador_redis(request: Request) -> VerificadorSaude:
    # `None` quando REDIS_URL não está configurada — ver `lifespan`.
    redis: Redis | None = request.app.state.redis
    if redis is None:
        return VerificadorDesativado()
    return VerificadorRedis(redis, get_settings().timeout_health_s)


def obter_repositorio_analises(request: Request) -> RepositorioAnalises:
    fabrica: async_sessionmaker[AsyncSession] = request.app.state.fabrica_de_sessoes
    return RepositorioAnalisesPostgres(fabrica)


@lru_cache
def obter_servico_analise() -> ServicoAnalise:
    """Uma instância por processo: as regex do `regras.yaml` são compiladas uma vez só.

    Recompilá-las a cada requisição custaria mais que a análise inteira e comeria o orçamento
    de 300ms das heurísticas locais (ADR-0002).
    """
    regras = carregar_regras()
    return ServicoAnalise(
        analisador=TextAnalyzer(regras),
        extrator=URLExtractor(regras.urls),
        motor=ScoringEngine(regras),
        maximo_de_caracteres=get_settings().texto_max_caracteres,
    )


def obter_orquestrador(
    servico: ServicoAnalise = Depends(obter_servico_analise),
    repositorio: RepositorioAnalises = Depends(obter_repositorio_analises),
) -> OrquestradorAnalise:
    return OrquestradorAnalise(servico, repositorio, get_settings().timeout_persistencia_s)
