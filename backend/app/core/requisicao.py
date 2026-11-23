"""Id da requisição e o log de cada requisição (ADR-0026).

Um middleware ASGI puro, e não o `BaseHTTPMiddleware` do Starlette: aquele embrulha o corpo do
pedido, e a rota do print lê o corpo aos pedaços, com teto (`_ler_corpo_limitado`).

O id vem do `X-Request-ID` que o proxy do Next gerou, se for um UUID na forma canônica; senão
nasce aqui. O backend é alcançável direto da internet: um valor qualquer nesse cabeçalho iria
parar em toda linha de log da requisição, por isso só UUID.

O log leva o TEMPLATE da rota (`/api/historico/{analise_id}`), nunca o caminho cru, a query string
nem o endereço de quem pediu.
"""

import logging
import uuid
from time import perf_counter

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logs import evento, request_id_atual
from app.core.metricas import contar_requisicao

logger = logging.getLogger(__name__)

CABECALHO = "X-Request-ID"
ROTA_NAO_MAPEADA = "nao_mapeada"
# Chamadas de máquina, frequentes e sem valor: o aquecimento da página (ADR-0017) e a coleta das
# métricas. Ficam fora do log por requisição e das métricas HTTP.
CAMINHOS_SEM_LOG = frozenset({"/health", "/metrics"})
# O método vira rótulo de métrica, e quem pede escolhe o texto dele: fora desta lista, um nome só.
METODOS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})


def id_da_requisicao(recebido: str | None) -> str:
    """O id recebido, se for um UUID canônico (minúsculo, com hifens); senão um novo."""
    if recebido:
        try:
            if str(uuid.UUID(recebido)) == recebido:
                return recebido
        except ValueError:
            pass
    return str(uuid.uuid4())


def rota_da_requisicao(scope: Scope) -> str:
    """O template da rota que atendeu. O roteador o deixa no `scope` quando acha a rota; sem
    rota (404), um nome fixo — o caminho cru é texto de quem pediu."""
    caminho: str | None = getattr(scope.get("route"), "path", None)
    return caminho or ROTA_NAO_MAPEADA


class MiddlewareDeRequisicao:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = id_da_requisicao(Headers(scope=scope).get(CABECALHO))
        marca = request_id_atual.set(request_id)
        inicio = perf_counter()
        # Se a aplicação levantar sem responder, quem responde é o Starlette, com 500.
        status = 500

        async def enviar(mensagem: Message) -> None:
            nonlocal status
            if mensagem["type"] == "http.response.start":
                status = mensagem["status"]
                MutableHeaders(scope=mensagem)[CABECALHO] = request_id
            await send(mensagem)

        try:
            await self.app(scope, receive, enviar)
        except Exception:
            self._registrar(scope, 500, inicio, falhou=True)
            raise
        else:
            self._registrar(scope, status, inicio, falhou=False)
        finally:
            request_id_atual.reset(marca)

    def _registrar(self, scope: Scope, status: int, inicio: float, *, falhou: bool) -> None:
        if scope["path"] in CAMINHOS_SEM_LOG:
            return
        metodo = scope["method"] if scope["method"] in METODOS else "OUTRO"
        rota = rota_da_requisicao(scope)
        duracao_s = perf_counter() - inicio
        contar_requisicao(metodo, rota, status, duracao_s)
        campos = evento(
            "requisicao",
            metodo=metodo,
            rota=rota,
            status=status,
            duracao_ms=round(duracao_s * 1000),
        )
        if falhou:
            # `exc_info` com a exceção em curso: o formatador tira dela só o tipo e a pilha.
            logger.error("requisicao", extra=campos, exc_info=True)
        else:
            logger.info("requisicao", extra=campos)
