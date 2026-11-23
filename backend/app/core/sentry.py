"""Rastreamento de erros com o Sentry (ADR-0026). Ligado só com `SENTRY_DSN`.

Sem DSN, `iniciar_sentry` não faz nada: nenhuma rede, nenhum efeito nos testes nem no CI.

O Sentry é um serviço de fora. A regra desta fatia vale em dobro aqui: nada do que a pessoa
mandou pode sair do processo. O SDK já ajuda (`send_default_pii=False`, corpo do pedido nunca,
sem variáveis locais), mas a garantia é o `limpar_evento`, que roda em todo evento e em toda
transação antes do envio e trabalha por lista do que PODE ficar no pedido.

Três cuidados que não são óbvios:

- **A mensagem da exceção nunca vai.** É nela que o conteúdo vaza: o erro de validação do
  Pydantic cita o valor recebido, o do driver do banco cita a linha, o da API da Anthropic pode
  citar o pedido. Ficam o tipo e a pilha, que é o que serve para achar o defeito.
- **As integrações automáticas ficam desligadas.** O SDK liga sozinho uma integração para cada
  biblioteca instalada. A da Anthropic captura por conta própria as exceções da chamada, mesmo
  as que o `AnalisadorIA` trata (toda queda no plano B viraria um erro no Sentry), e as do
  SQLAlchemy e do cliente HTTP anotam consultas e endereços. Entram só as do FastAPI.
- **Os logs não viram evento nem rastro.** Os nossos levam só metadado, mas os de bibliotecas
  não têm essa regra. O log já sai pelo terminal, com o mesmo `request_id`.
"""

from typing import Any, cast

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.types import Event, Hint

from app.core.config import Settings
from app.core.requisicao import ROTA_NAO_MAPEADA

# Cabeçalhos que nunca saem, em minúsculas. O SDK já mascara alguns sem `send_default_pii`; os
# do proxy (`x-verifyscan-*`) ele não conhece.
CABECALHOS_PROIBIDOS = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "x-forwarded-for",
        "x-real-ip",
        "forwarded",
        "x-verifyscan-ip",
        "x-verifyscan-segredo",
    }
)


def limpar_evento(evento_do_sdk: Event, _dica: Hint | None = None) -> Event:
    """Tira do evento tudo o que pode trazer dado de quem pediu. Serve de `before_send` e de
    `before_send_transaction`. Nunca descarta o evento: devolve o mesmo, mais magro."""
    # O `Event` do SDK é um dicionário com as chaves tipadas; aqui ele é tratado como dicionário
    # comum, porque a limpeza troca o formato do `request`.
    evento = cast(dict[str, Any], evento_do_sdk)
    pedido = evento.get("request")
    if isinstance(pedido, dict):
        # Por lista do que fica: método e cabeçalhos permitidos. Corpo (`data`), cookies, query
        # string, o endereço de quem pediu (`env`) e a URL (o caminho cru tem id de análise, e
        # um caminho que não existe tem o que alguém digitou) saem todos.
        limpo: dict[str, Any] = {}
        if "method" in pedido:
            limpo["method"] = pedido["method"]
        cabecalhos = pedido.get("headers")
        if isinstance(cabecalhos, dict):
            limpo["headers"] = {
                nome: valor
                for nome, valor in cabecalhos.items()
                if str(nome).lower() not in CABECALHOS_PROIBIDOS
            }
        evento["request"] = limpo
    # Quem é a pessoa, e o rastro do que aconteceu antes (logs, chamadas HTTP).
    evento.pop("user", None)
    evento.pop("breadcrumbs", None)
    # Texto livre de um log que virasse evento.
    evento.pop("logentry", None)
    evento.pop("message", None)
    for excecao in (evento.get("exception") or {}).get("values") or []:
        excecao.pop("value", None)
        for quadro in (excecao.get("stacktrace") or {}).get("frames") or []:
            quadro.pop("vars", None)
    # Sem rota casada, o nome da transação é o caminho cru.
    if (evento.get("transaction_info") or {}).get("source") != "route" and evento.get(
        "transaction"
    ):
        evento["transaction"] = ROTA_NAO_MAPEADA
    return evento_do_sdk


def iniciar_sentry(settings: Settings) -> bool:
    """Liga o Sentry se houver DSN. Devolve se ligou."""
    if settings.sentry_dsn is None:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment or settings.app_env,
        # Sem nenhum dos dois, `None`: o SDK segue sem versão.
        release=settings.app_version or settings.render_git_commit,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        # O corpo do pedido é a mensagem ou o print da pessoa.
        max_request_body_size="never",
        # Variável local de uma função da análise é o texto da mensagem.
        include_local_variables=False,
        max_breadcrumbs=0,
        auto_enabling_integrations=False,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
            LoggingIntegration(level=None, event_level=None),
        ],
        before_send=limpar_evento,
        before_send_transaction=limpar_evento,
    )
    return True
