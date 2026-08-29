"""Rota de análise. Fina: valida o corpo, chama o service, devolve o schema (CLAUDE.md §6)."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import obter_servico_analise
from app.schemas.analise import RespostaAnalise, SolicitacaoAnalise
from app.services.analise import EntradaInvalida, ServicoAnalise

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
    servico: ServicoAnalise = Depends(obter_servico_analise),
) -> RespostaAnalise:
    # O serviço é síncrono de propósito: nesta fase o pipeline é só CPU, com orçamento de
    # 300ms (ADR-0002), e não há I/O para aguardar. As chamadas externas chegam na Fase 4.
    try:
        return servico.analisar(solicitacao.texto)
    except EntradaInvalida as erro:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(erro)
        ) from erro
