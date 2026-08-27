"""Checagem de saúde das dependências de infraestrutura.

Cada verificador é uma implementação de `VerificadorSaude`, o que permite trocá-lo por um
falso determinístico nos testes sem tocar em rede.
"""

import asyncio
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Protocol

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.schemas.health import RespostaHealth, SaudeServico

TAMANHO_MAXIMO_DETALHE = 200


class VerificadorSaude(Protocol):
    """Contrato de uma checagem: não recebe nada, não levanta exceção, devolve o estado."""

    async def __call__(self) -> SaudeServico: ...


async def _executar(checagem: Callable[[], Awaitable[None]], timeout_s: float) -> SaudeServico:
    """Roda a checagem com timeout explícito e converte qualquer falha em `status='erro'`.

    Um endpoint de saúde que levanta exceção não informa nada; por isso o `except Exception`
    largo, que aqui é intencional e não um engolir erro por descuido.
    """
    inicio = perf_counter()
    try:
        async with asyncio.timeout(timeout_s):
            await checagem()
    except TimeoutError:
        return _resultado("erro", inicio, f"TimeoutError: timeout de {timeout_s}s excedido")
    except Exception as exc:
        return _resultado("erro", inicio, _resumir(exc))
    return _resultado("ok", inicio, None)


def _resultado(status: str, inicio: float, detalhe: str | None) -> SaudeServico:
    latencia_ms = round((perf_counter() - inicio) * 1000, 2)
    # `status` chega como str e o schema valida contra o Literal — se alguém passar outro
    # valor, o erro aparece aqui e não numa resposta HTTP silenciosamente errada.
    return SaudeServico.model_validate(
        {"status": status, "latencia_ms": latencia_ms, "detalhe": detalhe}
    )


def _resumir(exc: Exception) -> str:
    """Tipo da exceção e a primeira linha da mensagem, truncada.

    Só a primeira linha: erros de conexão do psycopg trazem várias, com host, porta e usuário.
    O que interessa para diagnóstico é o começo, e o corpo de /health é público.
    """
    primeira_linha = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
    resumo = f"{type(exc).__name__}: {primeira_linha}".strip().removesuffix(":")
    if len(resumo) > TAMANHO_MAXIMO_DETALHE:
        return resumo[: TAMANHO_MAXIMO_DETALHE - 1] + "…"
    return resumo


class VerificadorPostgres:
    """`SELECT 1` numa conexão do pool."""

    def __init__(self, engine: AsyncEngine, timeout_s: float) -> None:
        self._engine = engine
        self._timeout_s = timeout_s

    async def __call__(self) -> SaudeServico:
        return await _executar(self._consultar, self._timeout_s)

    async def _consultar(self) -> None:
        async with self._engine.connect() as conexao:
            await conexao.execute(text("SELECT 1"))


class VerificadorRedis:
    """`PING` no servidor."""

    def __init__(self, redis: Redis, timeout_s: float) -> None:
        self._redis = redis
        self._timeout_s = timeout_s

    async def __call__(self) -> SaudeServico:
        return await _executar(self._pingar, self._timeout_s)

    async def _pingar(self) -> None:
        await self._redis.ping()


async def verificar_saude(
    verificar_postgres: VerificadorSaude,
    verificar_redis: VerificadorSaude,
) -> RespostaHealth:
    """Roda as duas checagens em paralelo e agrega o estado geral."""
    postgres, redis = await asyncio.gather(verificar_postgres(), verificar_redis())
    tudo_ok = postgres.status == "ok" and redis.status == "ok"
    return RespostaHealth(
        status="ok" if tudo_ok else "degradado",
        postgres=postgres,
        redis=redis,
    )
