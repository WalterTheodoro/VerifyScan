"""GET /metrics, para o Prometheus (ADR-0026). Fina: confere o token e devolve o texto.

Sem `METRICS_TOKEN` a rota responde 404, como se não existisse: o backend é alcançável direto da
internet, e métrica aberta mostraria o volume de uso e o gasto do dia a qualquer um.
"""

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from app.core.config import Settings, get_settings
from app.core.metricas import exposicao

router = APIRouter(tags=["infraestrutura"])

_FORMATO = "text/plain; version=0.0.4; charset=utf-8"
_PREFIXO = "Bearer "


@router.get("/metrics", include_in_schema=False)
async def metricas(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Response:
    if settings.metrics_token is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    esperado = _PREFIXO + settings.metrics_token.get_secret_value()
    # `compare_digest`: o tempo da comparação não depende de quantos caracteres batem, então não
    # dá para descobrir o token aos poucos medindo a resposta. Em bytes, porque com texto fora do
    # ASCII ele levanta erro.
    if not hmac.compare_digest((authorization or "").encode(), esperado.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, headers={"WWW-Authenticate": "Bearer"}
        )
    return Response(content=exposicao(), media_type=_FORMATO)
