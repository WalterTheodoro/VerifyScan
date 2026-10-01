"""Rotas de conta: cadastro, login, logout e /eu. Finas: a regra está no ServicoAutenticacao.

O que é desta camada é o HTTP: status, mensagem em `detail` e o cookie `vs_sessao` (ADR-0013).
"""

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import NOME_DO_COOKIE, obter_servico_autenticacao, obter_usuario_atual
from app.core.config import Settings, get_settings
from app.schemas.autenticacao import RespostaUsuario, SolicitacaoCadastro, SolicitacaoLogin
from app.services.analise import EntradaInvalida
from app.services.autenticacao import (
    CredenciaisInvalidas,
    ServicoAutenticacao,
    ServicoIndisponivel,
)
from app.services.repositorio_usuarios import EmailJaCadastrado, UsuarioAutenticado

router = APIRouter(prefix="/api/auth", tags=["autenticação"])

_STATUS_DO_ERRO: dict[type[Exception], int] = {
    EntradaInvalida: status.HTTP_422_UNPROCESSABLE_CONTENT,
    EmailJaCadastrado: status.HTTP_409_CONFLICT,
    CredenciaisInvalidas: status.HTTP_401_UNAUTHORIZED,
    ServicoIndisponivel: status.HTTP_503_SERVICE_UNAVAILABLE,
}
_ERROS_DO_SERVICO = tuple(_STATUS_DO_ERRO)


def _http(erro: Exception) -> HTTPException:
    """A mensagem do service já é a frase em pt-BR para o usuário."""
    return HTTPException(status_code=_STATUS_DO_ERRO[type(erro)], detail=str(erro))


def _gravar_cookie(response: Response, token: str, settings: Settings) -> None:
    """HttpOnly, SameSite=Lax, Path=/ e SEM Domain (ADR-0013).

    Sem Domain, o cookie fica preso ao host que respondeu. Em produção esse host é o frontend,
    que repassa /api/* ao backend (fatia 3): onrender.com está na Public Suffix List, e um cookie
    do backend seria de terceiro para o frontend — o Safari bloqueia.
    """
    response.set_cookie(
        NOME_DO_COOKIE,
        token,
        max_age=settings.sessao_dias * 24 * 60 * 60,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _apagar_cookie(response: Response, settings: Settings) -> None:
    # Mesmos atributos da gravação: o navegador só apaga o cookie que bate com eles.
    response.delete_cookie(
        NOME_DO_COOKIE,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _resposta(usuario: UsuarioAutenticado) -> RespostaUsuario:
    return RespostaUsuario(nome=usuario.nome, email=usuario.email)


@router.post(
    "/cadastro",
    response_model=RespostaUsuario,
    status_code=status.HTTP_201_CREATED,
    summary="Cria a conta e já entra nela",
)
async def cadastrar(
    solicitacao: SolicitacaoCadastro,
    response: Response,
    servico: ServicoAutenticacao = Depends(obter_servico_autenticacao),
    settings: Settings = Depends(get_settings),
) -> RespostaUsuario:
    try:
        aberta = await servico.cadastrar(solicitacao.nome, solicitacao.email, solicitacao.senha)
    except _ERROS_DO_SERVICO as erro:
        raise _http(erro) from erro
    _gravar_cookie(response, aberta.token, settings)
    return _resposta(aberta.usuario)


@router.post("/login", response_model=RespostaUsuario, summary="Entra na conta")
async def entrar(
    solicitacao: SolicitacaoLogin,
    response: Response,
    servico: ServicoAutenticacao = Depends(obter_servico_autenticacao),
    settings: Settings = Depends(get_settings),
) -> RespostaUsuario:
    try:
        aberta = await servico.entrar(solicitacao.email, solicitacao.senha)
    except _ERROS_DO_SERVICO as erro:
        raise _http(erro) from erro
    _gravar_cookie(response, aberta.token, settings)
    return _resposta(aberta.usuario)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Sai da conta",
)
async def sair(
    servico: ServicoAutenticacao = Depends(obter_servico_autenticacao),
    settings: Settings = Depends(get_settings),
    token: str | None = Cookie(default=None, alias=NOME_DO_COOKIE),
) -> Response:
    """Apaga a sessão, se houver, e limpa o cookie SEMPRE — inclusive quando o banco não
    responde: o 503 é honesto sobre a sessão no servidor, e o navegador sai de qualquer jeito.
    """
    resposta: Response
    try:
        await servico.sair(token or "")
    except ServicoIndisponivel as erro:
        resposta = JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": str(erro)}
        )
    else:
        resposta = Response(status_code=status.HTTP_204_NO_CONTENT)
    _apagar_cookie(resposta, settings)
    return resposta


@router.get("/eu", response_model=RespostaUsuario, summary="Quem está logado")
async def eu(usuario: UsuarioAutenticado = Depends(obter_usuario_atual)) -> RespostaUsuario:
    return _resposta(usuario)
