"""Logs da aplicação: nível e saída do logger `app`, a partir de `LOG_LEVEL`.

Sem isto, ninguém configurava o logging: o root ficava em WARNING e todo INFO de `app.*` — a
latência e os tokens da IA (ADR-0020), por exemplo — sumia no Render.

Só o logger `app`, nunca o root: no root, o INFO ligaria também o do SQLAlchemy e o do cliente
HTTP. A propagação continua ligada, porque o `caplog` dos testes escuta no root.
"""

import logging

_FORMATO = "%(levelname)s %(name)s: %(message)s"


class _SaidaDoApp(logging.StreamHandler):  # type: ignore[type-arg]
    """Marca o handler deste módulo, para `criar_app()` não o empilhar a cada chamada."""


def configurar_logs(nivel: str) -> None:
    logger = logging.getLogger("app")
    logger.setLevel(nivel.upper())
    if not any(isinstance(handler, _SaidaDoApp) for handler in logger.handlers):
        saida = _SaidaDoApp()
        saida.setFormatter(logging.Formatter(_FORMATO))
        logger.addHandler(saida)
