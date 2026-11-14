"""Dependências das rotas.

Cada `obter_*` é o ponto de substituição usado pelos testes via `dependency_overrides`.
Engine, fábrica de sessões e cliente Redis vêm de `app.state`, onde o `lifespan` os deixou.
"""

from functools import lru_cache

from fastapi import Cookie, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.analyzers.dominios import DomainAnalyzer
from app.analyzers.texto import TextAnalyzer
from app.analyzers.urls import URLExtractor
from app.core.config import Settings, get_settings
from app.core.ip import chave_hmac, ip_do_visitante
from app.core.relogio import Relogio, agora_utc
from app.core.seguranca import HasherSenha
from app.formulator.analisador import AnalisadorIA
from app.formulator.cliente import ClienteAnthropic, ConsumoDaIA
from app.ocr.leitura import LeitorDePrint
from app.scoring.motor import ScoringEngine
from app.scoring.regras import carregar_regras
from app.scoring.respostas import carregar_respostas
from app.services.analise import ServicoAnalise
from app.services.autenticacao import ServicoAutenticacao, ServicoIndisponivel
from app.services.cota import ServicoCota
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
from app.services.repositorio_uso import RepositorioUso, RepositorioUsoPostgres
from app.services.repositorio_usuarios import (
    RepositorioUsuarios,
    RepositorioUsuariosPostgres,
    UsuarioAutenticado,
)
from app.services.tentativas import LimitadorDeTentativas

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
        dominios=DomainAnalyzer(regras),
        motor=ScoringEngine(regras),
        respostas=carregar_respostas(),
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


def obter_repositorio_uso(request: Request) -> RepositorioUso:
    fabrica: async_sessionmaker[AsyncSession] = request.app.state.fabrica_de_sessoes
    return RepositorioUsoPostgres(fabrica)


def obter_relogio() -> Relogio:
    """O relógio do dia da cota. Os testes o trocam pelo `RelogioFalso`."""
    return agora_utc


def obter_consumo() -> ConsumoDaIA:
    """Um por requisição: o FastAPI guarda o resultado de cada dependência durante a requisição,
    então o analisador, o leitor e o orquestrador recebem o MESMO objeto (ADR-0024)."""
    return ConsumoDaIA()


def obter_servico_cota(
    uso: RepositorioUso = Depends(obter_repositorio_uso),
    relogio: Relogio = Depends(obter_relogio),
    settings: Settings = Depends(get_settings),
) -> ServicoCota:
    return ServicoCota(
        uso,
        relogio,
        cota_sem_conta=settings.ia_cota_sem_conta,
        cota_com_conta=settings.ia_cota_com_conta,
        teto_usd=settings.ia_teto_gasto_diario_usd,
        preco_entrada_por_milhao=settings.ia_preco_entrada_usd_por_milhao,
        preco_saida_por_milhao=settings.ia_preco_saida_usd_por_milhao,
        cadastros_por_ip=settings.cadastros_por_ip_por_dia,
    )


def obter_chave_ip(request: Request, settings: Settings = Depends(get_settings)) -> str:
    """O HMAC do IP de quem pediu (ADR-0024). O IP puro não sai desta função: nem para o banco,
    nem para o log."""
    ip = ip_do_visitante(
        request.headers,
        request.client.host if request.client is not None else None,
        settings.proxy_segredo.get_secret_value(),
    )
    return chave_hmac(settings.ip_hmac_segredo.get_secret_value(), ip)


def obter_analisador_ia(
    request: Request, consumo: ConsumoDaIA = Depends(obter_consumo)
) -> AnalisadorIA:
    """O cliente da Anthropic nasce no `lifespan` (`None` com a IA desligada). Os testes trocam
    esta dependência por um falso: o `lifespan` não roda neles (ADR-0020)."""
    cliente: ClienteAnthropic | None = request.app.state.cliente_ia
    return AnalisadorIA(cliente, get_settings().ia_timeout_s, consumo)


def obter_leitor_de_print(
    request: Request, consumo: ConsumoDaIA = Depends(obter_consumo)
) -> LeitorDePrint:
    """O mesmo cliente da análise lê o print (ADR-0023): IA desligada, leitor indisponível. Os
    testes trocam esta dependência por um leitor com o `ClienteLeituraFalso`."""
    cliente: ClienteAnthropic | None = request.app.state.cliente_ia
    return LeitorDePrint(cliente, get_settings().ia_timeout_leitura_s, consumo)


def obter_orquestrador(
    servico: ServicoAnalise = Depends(obter_servico_analise),
    analisador_ia: AnalisadorIA = Depends(obter_analisador_ia),
    leitor: LeitorDePrint = Depends(obter_leitor_de_print),
    repositorio: RepositorioAnalises = Depends(obter_repositorio_analises),
    sessoes: RepositorioSessoes = Depends(obter_repositorio_sessoes),
    cota: ServicoCota = Depends(obter_servico_cota),
    consumo: ConsumoDaIA = Depends(obter_consumo),
    settings: Settings = Depends(get_settings),
) -> OrquestradorAnalise:
    return OrquestradorAnalise(
        servico=servico,
        analisador_ia=analisador_ia,
        respostas=carregar_respostas(),
        repositorio=repositorio,
        sessoes=sessoes,
        timeout_s=settings.timeout_persistencia_s,
        leitor=leitor,
        imagem_max_bytes=settings.imagem_max_bytes,
        timeout_ia_imagem_s=settings.ia_timeout_analise_imagem_s,
        maximo_de_caracteres=settings.texto_max_caracteres,
        cota=cota,
        consumo=consumo,
        timeout_cota_s=settings.timeout_cota_s,
    )


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
    """Uma instância por processo: o hash de mentira do login é gerado uma vez só, e o semáforo
    do Argon2 vale para o processo inteiro (ADR-0024).

    `criar_app` chama esta função na subida, para que o primeiro login não pague esse custo.
    """
    settings = get_settings()
    return HasherSenha(vagas=settings.argon2_simultaneos, espera_s=settings.timeout_autenticacao_s)


def criar_limitador(settings: Settings) -> LimitadorDeTentativas:
    return LimitadorDeTentativas(
        max_por_conta=settings.login_falhas_por_conta,
        max_por_ip=settings.login_falhas_por_ip,
        janela_s=settings.login_janela_minutos * 60,
    )


def obter_limitador(request: Request) -> LimitadorDeTentativas:
    """Nasce em `criar_app`, um por aplicação: em produção, um por processo; nos testes, cada app
    começa do zero, sem as falhas do teste anterior."""
    limitador: LimitadorDeTentativas = request.app.state.limitador
    return limitador


def obter_servico_autenticacao(
    usuarios: RepositorioUsuarios = Depends(obter_repositorio_usuarios),
    sessoes: RepositorioSessoes = Depends(obter_repositorio_sessoes),
    hasher: HasherSenha = Depends(obter_hasher),
    limitador: LimitadorDeTentativas = Depends(obter_limitador),
    cota: ServicoCota = Depends(obter_servico_cota),
    settings: Settings = Depends(get_settings),
) -> ServicoAutenticacao:
    return ServicoAutenticacao(
        usuarios=usuarios,
        sessoes=sessoes,
        hasher=hasher,
        sessao_dias=settings.sessao_dias,
        timeout_s=settings.timeout_autenticacao_s,
        limitador=limitador,
        segredo_das_chaves=settings.ip_hmac_segredo.get_secret_value(),
        cota=cota,
    )


def obter_servico_historico(
    repositorio: RepositorioHistorico = Depends(obter_repositorio_historico),
    sessoes: RepositorioSessoes = Depends(obter_repositorio_sessoes),
    uso: RepositorioUso = Depends(obter_repositorio_uso),
    relogio: Relogio = Depends(obter_relogio),
    settings: Settings = Depends(get_settings),
) -> ServicoHistorico:
    return ServicoHistorico(
        repositorio=repositorio,
        sessoes=sessoes,
        historico_dias=settings.historico_dias,
        timeout_s=settings.timeout_autenticacao_s,
        timeout_faxina_s=settings.timeout_persistencia_s,
        uso=uso,
        relogio=relogio,
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
