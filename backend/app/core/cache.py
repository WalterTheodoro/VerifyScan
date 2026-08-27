"""Cliente Redis. Usado como cache de reputação com TTL de 24h a partir da Fase 4."""

from redis.asyncio import Redis


def criar_redis(redis_url: str) -> Redis:
    """Cria o cliente. Não abre conexão aqui — o redis-py conecta sob demanda."""
    return Redis.from_url(redis_url, decode_responses=True)
