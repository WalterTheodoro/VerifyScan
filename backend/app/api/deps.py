"""Dependências das rotas.

Cada `obter_*` é o ponto de substituição usado pelos testes via `dependency_overrides`.
Engine, fábrica de sessões e cliente Redis vêm de `app.state`, onde o `lifespan` os deixou.
"""

from functools import lru_cache

from fastapi import Cookie, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.analyzers.texto import TextAnalyzer
from app.analyzers.urls import URLExtractor
from app.core.config import Settings, get_settings
from app.core.seguranca import HasherSenha
from app.scoring.motor import ScoringEngine
from app.scoring.regras import carregar_regras
from app.services.analise import ServicoAnalise
from app.services.autenticacao import ServicoAutenticacao, ServicoIndisponivel
from app.services.health import (
    VerificadorDesativado,
    VerificadorPostgres,
    VerificadorRedis,
    VerificadorSaude,
)
from app.services.historico import ServicoHistorico
from app.services.orquestrador import OrquestradorAnalise
from app.services.repositorio_analises import RepositorioAnalises, RepositorioAnalisesPostgres
from app.services.repositorio_historico import RepositorioHistorico, RepositorioHistoricoPostgres
from app.services.repositorio_sessoes import RepositorioSessoes, RepositorioSessoesPostgres
from app.services.repositorio_usuarios import (
    RepositorioUsuarios,
    RepositorioUsuariosPostgres,
    UsuarioAutenticado,
)

# Cookie da sessão opaca (ADR-0013). A rota de logout também o lê.
NOME_DO_COOKIE = "vs_sessao"


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


def obter_repositorio_usuarios(request: Request) -> RepositorioUsuarios:
    fabrica: async_sessionmaker[AsyncSession] = request.app.state.fabrica_de_sessoes
    return RepositorioUsuariosPostgres(fabrica)


def obter_repositorio_sessoes(request: Request) -> RepositorioSessoes:
    fabrica: async_sessionmaker[AsyncSession] = request.app.state.fabrica_de_sessoes
    return RepositorioSessoesPostgres(fabrica)


def obter_repositorio_historico(request: Request) -> RepositorioHistorico:
    fabrica: async_sessionmaker[AsyncSession] = request.app.state.fabrica_de_sessoes
    return RepositorioHistoricoPostgres(fabrica)


def obter_orquestrador(
    servico: ServicoAnalise = Depends(obter_servico_analise),
    repositorio: RepositorioAnalises = Depends(obter_repositorio_analises),
    sessoes: RepositorioSessoes = Depends(obter_repositorio_sessoes),
) -> OrquestradorAnalise:
    return OrquestradorAnalise(servico, repositorio, sessoes, get_settings().timeout_persistencia_s)


def ler_token_de_sessao(
    token: str | None = Cookie(default=None, alias=NOME_DO_COOKIE),
) -> str | None:
    """Só lê o cookie, sem consultar o banco.

    A análise não depende da conta: quem resolve o dono é o orquestrador, depois do resultado e
    dentro do teto do registro (ADR-0015). Por isso não há `obter_usuario_opcional`.
    """
    return token


@lru_cache
def obter_hasher() -> HasherSenha:
    """Uma instância por processo: o hash de mentira do login é gerado uma vez só.

    `criar_app` chama esta função na subida, para que o primeiro login não pague esse custo.
    """
    return HasherSenha()


def obter_servico_autenticacao(
    usuarios: RepositorioUsuarios = Depends(obter_repositorio_usuarios),
    sessoes: RepositorioSessoes = Depends(obter_repositorio_sessoes),
    hasher: HasherSenha = Depends(obter_hasher),
    settings: Settings = Depends(get_settings),
) -> ServicoAutenticacao:
    return ServicoAutenticacao(
        usuarios=usuarios,
        sessoes=sessoes,
        hasher=hasher,
        sessao_dias=settings.sessao_dias,
        timeout_s=settings.timeout_autenticacao_s,
    )


def obter_servico_historico(
    repositorio: RepositorioHistorico = Depends(obter_repositorio_historico),
    settings: Settings = Depends(get_settings),
) -> ServicoHistorico:
    return ServicoHistorico(
        repositorio=repositorio,
        historico_dias=settings.historico_dias,
        timeout_s=settings.timeout_autenticacao_s,
        timeout_desvinculacao_s=settings.timeout_persistencia_s,
    )


async def obter_usuario_atual(
    servico: ServicoAutenticacao = Depends(obter_servico_autenticacao),
    token: str | None = Cookie(default=None, alias=NOME_DO_COOKIE),
) -> UsuarioAutenticado:
    """Quem está logado, ou 401.

    Ponto único das rotas protegidas das próximas fatias, e substituível nos testes por
    `dependency_overrides`.
    """
    try:
        usuario = await servico.usuario_da_sessao(token or "")
    except ServicoIndisponivel as erro:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(erro)
        ) from erro
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Você precisa entrar na sua conta.",
        )
    return usuario
