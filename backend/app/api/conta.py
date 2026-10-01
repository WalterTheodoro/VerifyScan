"""Rotas da área "Minha conta": histórico (RF12) e dados da conta. Finas: a regra está nos
services; aqui só o HTTP (ADR-0015).

Todas exigem login por `obter_usuario_atual`, que já responde 401 sem sessão e 503 com o banco
lento.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import obter_servico_autenticacao, obter_servico_historico, obter_usuario_atual
from app.api.erros import ERRO_401, ERRO_404_ANALISE, ERRO_503
from app.schemas.conta import FatorHistorico, ItemHistorico, RespostaConta, RespostaHistorico
from app.services.autenticacao import ServicoAutenticacao, ServicoIndisponivel
from app.services.historico import AnaliseNaoEncontrada, ServicoHistorico
from app.services.repositorio_historico import AnaliseDoHistorico
from app.services.repositorio_usuarios import UsuarioAutenticado

router = APIRouter(prefix="/api", tags=["conta"])


def _http(erro: ServicoIndisponivel | AnaliseNaoEncontrada) -> HTTPException:
    """A mensagem do service já é a frase em pt-BR para o usuário."""
    codigo = (
        status.HTTP_404_NOT_FOUND
        if isinstance(erro, AnaliseNaoEncontrada)
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return HTTPException(status_code=codigo, detail=str(erro))


def _item(analise: AnaliseDoHistorico) -> ItemHistorico:
    return ItemHistorico(
        id=analise.id,
        created_at=analise.criada_em,
        nivel_risco=analise.nivel_risco,
        score_risco=analise.score,
        fatores=[
            FatorHistorico(categoria=f.categoria, descricao=f.descricao, peso=f.peso)
            for f in analise.fatores
        ],
    )


@router.get(
    "/historico",
    response_model=RespostaHistorico,
    summary="Análises feitas com a conta nos últimos dias",
    responses={**ERRO_401, **ERRO_503},
)
async def listar_historico(
    usuario: UsuarioAutenticado = Depends(obter_usuario_atual),
    servico: ServicoHistorico = Depends(obter_servico_historico),
) -> RespostaHistorico:
    try:
        analises = await servico.listar(usuario)
    except ServicoIndisponivel as erro:
        raise _http(erro) from erro
    return RespostaHistorico(dias=servico.dias, analises=[_item(a) for a in analises])


@router.delete(
    "/historico/{analise_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Apaga uma análise do histórico",
    responses={**ERRO_401, **ERRO_404_ANALISE, **ERRO_503},
)
async def apagar_analise(
    analise_id: str,
    usuario: UsuarioAutenticado = Depends(obter_usuario_atual),
    servico: ServicoHistorico = Depends(obter_servico_historico),
) -> Response:
    # `str`, e não `uuid.UUID`: id malformado recebe o mesmo 404 em pt-BR, não o 422 em inglês.
    try:
        await servico.apagar(usuario, analise_id)
    except (AnaliseNaoEncontrada, ServicoIndisponivel) as erro:
        raise _http(erro) from erro
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/historico",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Apaga todo o histórico da conta",
    responses={**ERRO_401, **ERRO_503},
)
async def apagar_historico(
    usuario: UsuarioAutenticado = Depends(obter_usuario_atual),
    servico: ServicoHistorico = Depends(obter_servico_historico),
) -> Response:
    try:
        await servico.apagar_todas(usuario)
    except ServicoIndisponivel as erro:
        raise _http(erro) from erro
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/conta",
    response_model=RespostaConta,
    summary="Dados da conta de quem está logado",
    responses={**ERRO_401, **ERRO_503},
)
async def dados_da_conta(
    usuario: UsuarioAutenticado = Depends(obter_usuario_atual),
    servico: ServicoAutenticacao = Depends(obter_servico_autenticacao),
) -> RespostaConta:
    try:
        dados = await servico.dados_da_conta(usuario)
    except ServicoIndisponivel as erro:
        raise _http(erro) from erro
    if dados is None:
        # A conta sumiu entre a checagem da sessão e esta consulta: para a tela, é "deslogado".
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Você precisa entrar na sua conta.",
        )
    return RespostaConta(nome=dados.nome, email=dados.email, criado_em=dados.criado_em)
