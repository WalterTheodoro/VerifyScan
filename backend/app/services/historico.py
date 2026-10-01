"""Histórico da conta: listar, apagar e desvincular o que passou da janela (ADR-0015).

Dois tetos, escolhidos pelo modo de falha, como no ADR-0013:
- **o que a pessoa pediu** (listar, apagar) usa `timeout_autenticacao_s`; estourou, 503 com
  "tente de novo";
- **a desvinculação** é faxina oportunista: usa `timeout_persistencia_s`, e estourar ou falhar
  só vira log. Na leitura nada fora da janela aparece nunca, rode ela ou não.
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

from app.services.autenticacao import ServicoIndisponivel
from app.services.repositorio_historico import AnaliseDoHistorico, RepositorioHistorico
from app.services.repositorio_usuarios import UsuarioAutenticado

logger = logging.getLogger(__name__)

# Teto da listagem. Sem paginação nesta fatia: 7 dias de uso de uma pessoa cabem com folga.
LIMITE_DA_LISTAGEM = 200


class AnaliseNaoEncontrada(Exception):
    """A mesma resposta para id inexistente, inválido e de outra pessoa: não revela existência."""

    def __init__(self) -> None:
        super().__init__("Não encontramos esta análise.")


async def desvincular_vencidas(
    repositorio: RepositorioHistorico, historico_dias: int, timeout_s: float
) -> None:
    """Tira o dono das análises que passaram da janela. Nunca levanta.

    Roda sem agendador, nos dois momentos em que o processo já está acordado: na subida (lifespan)
    e a cada listagem. O log leva só o tipo da exceção, como no registro (ADR-0012).
    """
    try:
        async with asyncio.timeout(timeout_s):
            await repositorio.desvincular_vencidas(timedelta(days=historico_dias))
    except Exception as exc:
        logger.warning("Desvinculação do histórico não rodou: %s", type(exc).__name__)


class ServicoHistorico:
    def __init__(
        self,
        repositorio: RepositorioHistorico,
        historico_dias: int,
        timeout_s: float,
        timeout_desvinculacao_s: float,
    ) -> None:
        self._repositorio = repositorio
        self._historico_dias = historico_dias
        self._timeout_s = timeout_s
        self._timeout_desvinculacao_s = timeout_desvinculacao_s

    @property
    def dias(self) -> int:
        return self._historico_dias

    async def listar(self, usuario: UsuarioAutenticado) -> list[AnaliseDoHistorico]:
        await desvincular_vencidas(
            self._repositorio, self._historico_dias, self._timeout_desvinculacao_s
        )
        async with self._banco():
            return await self._repositorio.listar(
                usuario.id, timedelta(days=self._historico_dias), LIMITE_DA_LISTAGEM
            )

    async def apagar(self, usuario: UsuarioAutenticado, analise_id: str) -> None:
        """O id chega como texto: malformado também é 404, e não o 422 em inglês do FastAPI."""
        try:
            id_valido = uuid.UUID(analise_id)
        except ValueError as erro:
            raise AnaliseNaoEncontrada() from erro
        async with self._banco():
            apagada = await self._repositorio.apagar(usuario.id, id_valido)
        if not apagada:
            raise AnaliseNaoEncontrada()

    async def apagar_todas(self, usuario: UsuarioAutenticado) -> None:
        async with self._banco():
            await self._repositorio.apagar_todas(usuario.id)

    @asynccontextmanager
    async def _banco(self) -> AsyncIterator[None]:
        """Teto do I/O de banco (ADR-0002). Estourou: 503 ao usuário, como na autenticação."""
        try:
            async with asyncio.timeout(self._timeout_s):
                yield
        except TimeoutError as erro:
            logger.warning("Banco não respondeu em %.1f s no histórico", self._timeout_s)
            raise ServicoIndisponivel() from erro
