"""Rota de análise. Fina: valida o corpo, chama o service, devolve o schema (CLAUDE.md §6)."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import obter_orquestrador
from app.schemas.analise import RespostaAnalise, SolicitacaoAnalise
from app.services.analise import EntradaInvalida
from app.services.orquestrador import OrquestradorAnalise

router = APIRouter(prefix="/api", tags=["análise"])


@router.post(
    "/analises",
    response_model=RespostaAnalise,
    summary="Analisa uma mensagem suspeita e devolve o nível de risco",
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Conteúdo que não dá para analisar. `detail` é a mensagem ao usuário."
        }
    },
)
async def criar_analise(
    solicitacao: SolicitacaoAnalise,
    orquestrador: OrquestradorAnalise = Depends(obter_orquestrador),
) -> RespostaAnalise:
    # A análise em si é síncrona e só CPU (orçamento de 300ms, ADR-0002); o orquestrador
    # acrescenta o registro no banco, que tem timeout próprio e nunca derruba a resposta.
    try:
        return await orquestrador.analisar(solicitacao.texto)
    except EntradaInvalida as erro:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(erro)
        ) from erro
