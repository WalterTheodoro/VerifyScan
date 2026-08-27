"""Rota de saúde. Fina: chama o service, escolhe o código HTTP, devolve o schema."""

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import obter_verificador_postgres, obter_verificador_redis
from app.schemas.health import RespostaHealth
from app.services.health import VerificadorSaude, verificar_saude

router = APIRouter(tags=["infraestrutura"])


@router.get(
    "/health",
    response_model=RespostaHealth,
    summary="Estado da API e de cada dependência",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": RespostaHealth}},
)
async def health(
    response: Response,
    verificar_postgres: VerificadorSaude = Depends(obter_verificador_postgres),
    verificar_redis: VerificadorSaude = Depends(obter_verificador_redis),
) -> RespostaHealth:
    resultado = await verificar_saude(verificar_postgres, verificar_redis)
    if resultado.status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return resultado
