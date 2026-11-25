"""Logs da aplicação: nível, formato e saída do logger `app` (`LOG_LEVEL`, `LOG_FORMAT`).

Sem isto, ninguém configurava o logging: o root ficava em WARNING e todo INFO de `app.*` — a
latência e os tokens da IA (ADR-0020), por exemplo — sumia no Render.

Só o logger `app`, nunca o root: no root, o INFO ligaria também o do SQLAlchemy e o do cliente
HTTP. A propagação continua ligada, porque o `caplog` dos testes escuta no root.

O log de acesso do uvicorn sai desligado (fatia 10, ADR-0024). Cada linha dele começa pelo
endereço de quem pediu, e o uvicorn troca esse endereço pelo do `X-Forwarded-For` quando a conexão
vem de um proxy em que ele confia — medido localmente: o IP do visitante ia para o log. O IP nunca
é logado, e isso não pode depender de lembrar uma opção no comando de start do Render. Quem loga
cada requisição é o middleware de `app/core/requisicao.py`, sem endereço nenhum.

Formato (ADR-0026): uma linha JSON por log, com `ts`, `nivel`, `evento`, `request_id` e os campos
do evento. Um log sem evento sai como `evento: "log"`, com a `mensagem`. De uma exceção saem só o
tipo e a pilha (arquivo:linha:função): nunca a mensagem dela, que pode citar o que a pessoa mandou
(erro de validação) ou valores da linha (erro do driver).
"""

import json
import logging
import traceback
from contextvars import ContextVar
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Literal

FormatoDeLog = Literal["json", "texto"]

# O id da requisição em curso. Quem preenche é o middleware; fora de uma requisição (subida,
# faxina) fica `None`. Contextvar: cada requisição enxerga só o seu, mesmo com várias em paralelo.
request_id_atual: ContextVar[str | None] = ContextVar("request_id_atual", default=None)

_CAMPOS_FIXOS = ("ts", "nivel", "evento", "request_id", "logger", "mensagem", "erro", "pilha")


def evento(nome: str, **campos: object) -> dict[str, object]:
    """O `extra=` de um log que é um evento de domínio: `logger.info("...", extra=evento(...))`.

    Só metadado nos campos: tipo, nível, duração, status, motivo. Nunca o conteúdo da mensagem,
    e-mail, IP, id de usuário nem nada da regra de privacidade do ADR-0026.
    """
    return {"evento": nome, "campos": campos}


def _pilha(tb: TracebackType | None) -> list[str]:
    """Arquivo, linha e função de cada quadro. Sem a linha de código e sem variáveis."""
    return [f"{q.filename}:{q.lineno}:{q.name}" for q in traceback.extract_tb(tb)]


class FormatadorJSON(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        nome_do_evento: str = getattr(record, "evento", "log")
        dados: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "nivel": record.levelname,
            "evento": nome_do_evento,
            "request_id": request_id_atual.get(),
            "logger": record.name,
        }
        mensagem = record.getMessage()
        if mensagem != nome_do_evento:
            dados["mensagem"] = mensagem
        # Um campo do evento nunca troca um campo fixo.
        campos: dict[str, object] = getattr(record, "campos", {})
        dados.update({k: v for k, v in campos.items() if k not in _CAMPOS_FIXOS})
        if record.exc_info and record.exc_info[0] is not None:
            dados["erro"] = record.exc_info[0].__name__
            dados["pilha"] = _pilha(record.exc_info[2])
        return json.dumps(dados, ensure_ascii=False, default=str)


class FormatadorTexto(logging.Formatter):
    """O formato legível, para o terminal de desenvolvimento (`LOG_FORMAT=texto`)."""

    def format(self, record: logging.LogRecord) -> str:
        linha = f"{record.levelname} {record.name}: {record.getMessage()}"
        nome_do_evento: str | None = getattr(record, "evento", None)
        if nome_do_evento is not None:
            campos: dict[str, object] = getattr(record, "campos", {})
            detalhes = " ".join(f"{k}={v}" for k, v in campos.items())
            linha += f" [{nome_do_evento} {detalhes}]" if detalhes else f" [{nome_do_evento}]"
        if record.exc_info and record.exc_info[0] is not None:
            # A mesma regra do JSON: tipo e pilha, nunca a mensagem da exceção.
            linha += f" | {record.exc_info[0].__name__} em " + " < ".join(
                reversed(_pilha(record.exc_info[2]))
            )
        return linha


class _SaidaDoApp(logging.StreamHandler):  # type: ignore[type-arg]
    """Marca o handler deste módulo, para `criar_app()` não o empilhar a cada chamada."""


def configurar_logs(nivel: str, formato: FormatoDeLog = "json") -> None:
    logger = logging.getLogger("app")
    logger.setLevel(nivel.upper())
    saida = next((h for h in logger.handlers if isinstance(h, _SaidaDoApp)), None)
    if saida is None:
        saida = _SaidaDoApp()
        logger.addHandler(saida)
    saida.setFormatter(FormatadorTexto() if formato == "texto" else FormatadorJSON())
    # O uvicorn loga a exceção não tratada com o traceback inteiro, e a mensagem de uma exceção
    # pode citar o que a pessoa mandou. Os logs dele passam a sair pelo mesmo handler: mesmo
    # formato, e da exceção só o tipo e a pilha (ADR-0026).
    servidor = logging.getLogger("uvicorn")
    servidor.handlers[:] = [saida]
    servidor.propagate = False
    logging.getLogger("uvicorn.access").disabled = True
    # O httpx registra em INFO a URL de cada chamada, e a do Safe Browsing leva a chave na
    # query (ADR-0028). Desligados de vez: mesmo que alguém baixe o nível do log raiz, a URL
    # não sai.
    for nome in ("httpx", "httpcore"):
        logging.getLogger(nome).disabled = True
