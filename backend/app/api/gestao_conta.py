"""Rotas que mudam a credencial ou apagam a conta: trocar senha e excluir (ADR-0019).

Ficam fora de `api/conta.py`, que só lê (histórico e dados): estas pedem a senha de novo, mexem
nas sessões e no cookie. Finas, como as outras: a regra está no `ServicoAutenticacao`.

Senha errada é 400, nunca 401. A sessão continua válida, e o frontend trata 401 como "deslogado".
"""

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status

from app.api.autenticacao import apagar_cookie
from app.api.deps import NOME_DO_COOKIE, obter_servico_autenticacao, obter_usuario_atual
from app.api.erros import ERRO_400_SENHA, ERRO_401, ERRO_422, ERRO_503
from app.core.config import Settings, get_settings
from app.schemas.autenticacao import SolicitacaoExclusao, SolicitacaoTrocaSenha
from app.services.analise import EntradaInvalida
from app.services.autenticacao import (
    ContaNaoEncontrada,
    SenhaIncorreta,
    ServicoAutenticacao,
    ServicoIndisponivel,
)
from app.services.repositorio_usuarios import UsuarioAutenticado

router = APIRouter(prefix="/api/conta", tags=["conta"])

_STATUS_DO_ERRO: dict[type[Exception], int] = {
    SenhaIncorreta: status.HTTP_400_BAD_REQUEST,
    ContaNaoEncontrada: status.HTTP_401_UNAUTHORIZED,
    EntradaInvalida: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ServicoIndisponivel: status.HTTP_503_SERVICE_UNAVAILABLE,
}
_ERROS_DO_SERVICO = tuple(_STATUS_DO_ERRO)


def _http(erro: Exception) -> HTTPException:
    """A mensagem do service já é a frase em pt-BR para o usuário."""
    return HTTPException(status_code=_STATUS_DO_ERRO[type(erro)], detail=str(erro))


@router.post(
    "/senha",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Troca a senha e encerra as outras sessões da conta",
    responses={**ERRO_400_SENHA, **ERRO_401, **ERRO_422, **ERRO_503},
)
async def trocar_senha(
    solicitacao: SolicitacaoTrocaSenha,
    usuario: UsuarioAutenticado = Depends(obter_usuario_atual),
    servico: ServicoAutenticacao = Depends(obter_servico_autenticacao),
    token: str | None = Cookie(default=None, alias=NOME_DO_COOKIE),
) -> Response:
    # O token identifica a sessão deste aparelho, a única que sobrevive à troca.
    try:
        await servico.trocar_senha(
            usuario, token or "", solicitacao.senha_atual, solicitacao.nova_senha
        )
    except _ERROS_DO_SERVICO as erro:
        raise _http(erro) from erro
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/excluir",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Exclui a conta, as sessões e todo o histórico",
    responses={**ERRO_400_SENHA, **ERRO_401, **ERRO_503},
)
async def excluir_conta(
    solicitacao: SolicitacaoExclusao,
    usuario: UsuarioAutenticado = Depends(obter_usuario_atual),
    servico: ServicoAutenticacao = Depends(obter_servico_autenticacao),
    settings: Settings = Depends(get_settings),
) -> Response:
    """POST, e não DELETE: o corpo leva a senha, e DELETE com corpo é mal suportado por proxies.

    O cookie só é limpo quando a conta foi de fato apagada. Com senha errada ou banco fora, a
    pessoa continua logada, porque continua logada de verdade.
    """
    try:
        await servico.excluir_conta(usuario, solicitacao.senha)
    except _ERROS_DO_SERVICO as erro:
        raise _http(erro) from erro
    resposta = Response(status_code=status.HTTP_204_NO_CONTENT)
    apagar_cookie(resposta, settings)
    return resposta
