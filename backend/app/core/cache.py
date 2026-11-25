"""Cliente Redis. Hoje sem uso: o cache de reputação que o RFC previa aqui ficou no Postgres,
porque o Redis está desligado em produção (ADR-0028). Só o `/health` o consulta."""

from redis.asyncio import Redis


def criar_redis(redis_url: str) -> Redis:
    """Cria o cliente. Não abre conexão aqui — o redis-py conecta sob demanda."""
    return Redis.from_url(redis_url, decode_responses=True)
