"""Orquestração async da análise: analisar → registrar.

O `ServicoAnalise` continua síncrono e puro — é ele que o `avaliar_corpus` chama, sem banco.
O I/O fica aqui, numa camada fina por cima, e a rota chama um método só.
"""

import asyncio
import logging

from app.schemas.analise import RespostaAnalise
from app.services.analise import ServicoAnalise
from app.services.repositorio_analises import RegistroAnalise, RepositorioAnalises

logger = logging.getLogger(__name__)


class OrquestradorAnalise:
    def __init__(
        self,
        servico: ServicoAnalise,
        repositorio: RepositorioAnalises,
        timeout_s: float,
    ) -> None:
        self._servico = servico
        self._repositorio = repositorio
        self._timeout_s = timeout_s

    async def analisar(self, texto: str) -> RespostaAnalise:
        """`EntradaInvalida` propaga sem registrar: o que não foi analisado não pontuou."""
        resposta = self._servico.analisar(texto)
        await self._registrar(RegistroAnalise.da_resposta(resposta, tipo_input="texto"))
        return resposta

    async def _registrar(self, registro: RegistroAnalise) -> None:
        """Falha ao registrar nunca derruba a análise (ADR-0012; filosofia das invariantes 3 e 4).

        O `except Exception` largo é intencional: banco fora, timeout e erro de integridade têm o
        mesmo destino. A transação é descartada pelo repositório. O log leva só o tipo da
        exceção — a mensagem de erro do driver pode citar valores da linha.
        """
        try:
            async with asyncio.timeout(self._timeout_s):
                await self._repositorio.registrar(registro)
        except Exception as exc:
            logger.warning("Registro da análise descartado: %s", type(exc).__name__)
