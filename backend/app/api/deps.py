"""Dependências das rotas.

Cada `obter_*` é o ponto de substituição usado pelos testes via `dependency_overrides`.
Engine e cliente Redis vêm de `app.state`, onde o `lifespan` os deixou.
"""

from functools import lru_cache

from fastapi import Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from app.analyzers.texto import TextAnalyzer
from app.analyzers.urls import URLExtractor
from app.core.config import get_settings
from app.scoring.motor import ScoringEngine
from app.scoring.regras import carregar_regras
from app.services.analise import ServicoAnalise
from app.services.health import VerificadorPostgres, VerificadorRedis, VerificadorSaude


def obter_verificador_postgres(request: Request) -> VerificadorSaude:
    engine: AsyncEngine = request.app.state.engine
    return VerificadorPostgres(engine, get_settings().timeout_health_s)


def obter_verificador_redis(request: Request) -> VerificadorSaude:
    redis: Redis = request.app.state.redis
    return VerificadorRedis(redis, get_settings().timeout_health_s)


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
