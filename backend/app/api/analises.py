"""Rotas de análise. Finas: validam o corpo, chamam o service, devolvem o schema (CLAUDE.md §6)."""

import base64
import math

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError

from app.api.deps import ler_token_de_sessao, obter_orquestrador
from app.core.config import Settings, get_settings
from app.schemas.analise import RespostaAnalise, SolicitacaoAnalise, SolicitacaoAnalisePrint
from app.services.analise import EntradaInvalida
from app.services.orquestrador import LeituraIndisponivel, OrquestradorAnalise

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
    token: str | None = Depends(ler_token_de_sessao),
) -> RespostaAnalise:
    # A análise em si é síncrona e só CPU (orçamento de 300ms, ADR-0002); o orquestrador
    # acrescenta o registro no banco, que tem timeout próprio e nunca derruba a resposta. O
    # token só serve ao registro, para ligar a análise à conta (ADR-0015).
    try:
        return await orquestrador.analisar(solicitacao.texto, token)
    except EntradaInvalida as erro:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(erro)
        ) from erro


_IMAGEM_INVALIDA = "Não recebemos uma imagem válida. Escolha o print de novo e tente outra vez."
_GRANDE_DEMAIS = "Esta imagem é grande demais. Envie um print da tela, sem ampliar."
# Folga para o JSON e para o texto que a pessoa escreveu junto (até 5000 caracteres, até 4 bytes
# cada em UTF-8).
_FOLGA_DO_CORPO = 64 * 1024


def _limite_do_corpo(settings: Settings) -> int:
    """A imagem em base64 ocupa 4/3 dos bytes dela (ADR-0023)."""
    return math.ceil(settings.imagem_max_bytes * 4 / 3) + _FOLGA_DO_CORPO


async def _ler_corpo_limitado(request: Request, limite: int) -> bytes:
    """Lê o corpo aos pedaços e para no limite: um corpo gigante não chega inteiro à memória.

    O Starlette não tem limite de corpo para JSON. O Content-Length é conferido antes, mas não
    basta sozinho: com `Transfer-Encoding: chunked` ele nem vem.
    """
    declarado = request.headers.get("content-length")
    if declarado is not None and declarado.isdigit() and int(declarado) > limite:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=_GRANDE_DEMAIS)
    partes: list[bytes] = []
    tamanho = 0
    async for parte in request.stream():
        tamanho += len(parte)
        if tamanho > limite:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=_GRANDE_DEMAIS
            )
        partes.append(parte)
    return b"".join(partes)


@router.post(
    "/analises/imagem",
    response_model=RespostaAnalise,
    summary="Analisa o print de uma conversa: lê o texto e analisa o que a pessoa recebeu",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {"schema": SolicitacaoAnalisePrint.model_json_schema()}
            },
        }
    },
    responses={
        status.HTTP_413_CONTENT_TOO_LARGE: {"description": "Corpo acima do limite da imagem."},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": (
                "Imagem inválida, print que não deu para ler, sem mensagem recebida ou com texto "
                "demais. Sem nível. `detail` é a mensagem ao usuário."
            )
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "A IA está desligada."},
    },
)
async def criar_analise_de_print(
    request: Request,
    orquestrador: OrquestradorAnalise = Depends(obter_orquestrador),
    token: str | None = Depends(ler_token_de_sessao),
    settings: Settings = Depends(get_settings),
) -> RespostaAnalise:
    # JSON com base64, e não multipart: o `UploadFile` do Starlette grava em arquivo temporário
    # acima de 1 MB, e a imagem não pode tocar o disco (invariante 2, ADR-0023). O corpo é lido à
    # mão, com teto, e o erro de validação sai em pt-BR, não no formato do FastAPI.
    corpo = await _ler_corpo_limitado(request, _limite_do_corpo(settings))
    try:
        solicitacao = SolicitacaoAnalisePrint.model_validate_json(corpo)
        imagem = base64.b64decode(solicitacao.imagem_base64, validate=True)
    except (ValidationError, ValueError) as erro:
        # ValueError: base64 inválido (`binascii.Error` é um) ou com caractere fora do ASCII.
        # O log fica sem nada: a mensagem do erro de validação cita o conteúdo.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=_IMAGEM_INVALIDA
        ) from erro
    try:
        return await orquestrador.analisar_print(imagem, solicitacao.texto, token)
    except EntradaInvalida as erro:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(erro)
        ) from erro
    except LeituraIndisponivel as erro:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(erro)
        ) from erro
