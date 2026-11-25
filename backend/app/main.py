"""Ponto de entrada da API.

uv run uvicorn app.main:app --port 8000 --loop none --reload
"""

import asyncio
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.analises import router as router_analises
from app.api.autenticacao import router as router_autenticacao
from app.api.conta import router as router_conta
from app.api.deps import criar_limitador, obter_hasher
from app.api.gestao_conta import router as router_gestao_conta
from app.api.health import router as router_health
from app.api.metricas import router as router_metricas
from app.core.cache import criar_redis
from app.core.config import get_settings
from app.core.db import criar_engine, criar_sessionmaker
from app.core.logs import configurar_logs, evento
from app.core.relogio import agora_utc, dia_de_sao_paulo
from app.core.requisicao import MiddlewareDeRequisicao
from app.core.sentry import iniciar_sentry
from app.formulator.cliente import criar_cliente_ia
from app.scoring.regras import carregar_regras
from app.scoring.respostas import carregar_respostas
from app.services.historico import faxina
from app.services.repositorio_historico import RepositorioHistoricoPostgres
from app.services.repositorio_sessoes import RepositorioSessoesPostgres
from app.services.repositorio_uso import RepositorioUsoPostgres

# No Windows o event loop padrão do asyncio é o Proactor, e o psycopg em modo async se recusa a
# rodar nele. Trocar a política aqui, na importação do módulo, é o que faz qualquer processo que
# importe a aplicação nascer com o Selector — o mesmo guard do alembic/env.py.
logger = logging.getLogger(__name__)

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Cria engine e cliente Redis uma vez por processo e fecha os dois na saída.

    Nenhum dos dois abre conexão aqui: ambos conectam sob demanda. Quem quiser saber se a
    infraestrutura responde deve chamar /health.

    Sem REDIS_URL o cliente não é criado e `app.state.redis` fica `None`: é o Redis desativado,
    estado de produção (nada o usa hoje: ADR-0028). Com a IA desligada, `app.state.cliente_ia`
    também fica `None`, e toda análise sai com o plano B (ADR-0020).

    A única I/O da subida é a faxina do que venceu — análises do histórico, sessões e o uso
    diário da IA (ADR-0015, ADR-0019, ADR-0024): oportunista, com o teto do registro, e nunca
    derruba o processo — se o banco estiver fora, só loga.
    """
    settings = get_settings()
    engine = criar_engine(settings.database_url)
    redis = criar_redis(settings.redis_url) if settings.redis_url else None
    app.state.engine = engine
    app.state.fabrica_de_sessoes = criar_sessionmaker(engine)
    app.state.redis = redis
    cliente_ia = criar_cliente_ia(settings)
    app.state.cliente_ia = cliente_ia
    # Um cliente HTTP só para as bases de reputação (ADR-0028), sem seguir redirecionamento.
    # O teto de cada chamada é passado na própria chamada.
    http_reputacao = httpx.AsyncClient(follow_redirects=False)
    app.state.http_reputacao = http_reputacao
    if cliente_ia is None:
        # Uma vez por processo, e não a cada análise: IA desligada é configuração, não falha.
        logger.info("IA desligada: as análises saem só do motor", extra=evento("ia_desligada"))
    await faxina(
        RepositorioHistoricoPostgres(app.state.fabrica_de_sessoes),
        RepositorioSessoesPostgres(app.state.fabrica_de_sessoes),
        settings.historico_dias,
        settings.timeout_persistencia_s,
        uso=RepositorioUsoPostgres(app.state.fabrica_de_sessoes),
        hoje=dia_de_sao_paulo(agora_utc()),
    )
    try:
        yield
    finally:
        if redis is not None:
            await redis.aclose()
        if cliente_ia is not None:
            await cliente_ia.sdk.close()
        await http_reputacao.aclose()
        await engine.dispose()


def criar_app() -> FastAPI:
    settings = get_settings()
    configurar_logs(settings.log_level, settings.log_format)
    # Antes de criar a app: o SDK se prende ao FastAPI na criação dela. Sem `SENTRY_DSN`, nada
    # acontece (ADR-0026).
    iniciar_sentry(settings)
    # Aqui, e não no `lifespan`: um `regras.yaml` ou `respostas.yaml` quebrado precisa derrubar
    # o processo na subida, e não a primeira requisição do usuário. Fica antes de qualquer rota.
    carregar_regras()
    carregar_respostas()
    # O hash de mentira do login (ADR-0013) nasce aqui, uma vez por processo: no primeiro login,
    # aquela resposta pagaria o custo e sairia mais lenta que as outras.
    obter_hasher()
    app = FastAPI(
        title="VerifyScan",
        description="Análise de mensagens suspeitas: nível de risco, fatores e recomendação.",
        version="0.1.0",
        lifespan=lifespan,
    )
    # Aqui, e não no `lifespan`: não abre conexão, e os testes (que não rodam o `lifespan`) também
    # precisam de um — novo a cada app, sem as falhas do teste anterior (ADR-0024).
    app.state.limitador = criar_limitador(settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origens_cors,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Por último: o middleware acrescentado por último é o de fora, então o id da requisição
    # existe antes de qualquer outro código rodar, e o log vê a resposta final (ADR-0026).
    app.add_middleware(MiddlewareDeRequisicao)
    app.include_router(router_health)
    app.include_router(router_metricas)
    app.include_router(router_analises)
    app.include_router(router_autenticacao)
    app.include_router(router_conta)
    app.include_router(router_gestao_conta)
    return app


app = criar_app()
