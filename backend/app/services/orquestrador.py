"""Orquestração async da análise: analisar → registrar.

O `ServicoAnalise` continua síncrono e puro — é ele que o `avaliar_corpus` chama, sem banco.
O I/O fica aqui, numa camada fina por cima, e a rota chama um método só.
"""

import asyncio
import dataclasses
import logging
import uuid

from app.schemas.analise import RespostaAnalise
from app.services.analise import ServicoAnalise
from app.services.autenticacao import hash_do_token
from app.services.repositorio_analises import RegistroAnalise, RepositorioAnalises
from app.services.repositorio_sessoes import RepositorioSessoes

logger = logging.getLogger(__name__)


class OrquestradorAnalise:
    def __init__(
        self,
        servico: ServicoAnalise,
        repositorio: RepositorioAnalises,
        sessoes: RepositorioSessoes,
        timeout_s: float,
    ) -> None:
        self._servico = servico
        self._repositorio = repositorio
        self._sessoes = sessoes
        self._timeout_s = timeout_s

    async def analisar(self, texto: str, token_de_sessao: str | None = None) -> RespostaAnalise:
        """`EntradaInvalida` propaga sem registrar: o que não foi analisado não pontuou.

        A análise não sabe quem é a pessoa; só o registro precisa saber (ADR-0015). Por isso o
        resultado sai antes de qualquer consulta à sessão, e o dono é resolvido dentro do teto
        do registro.
        """
        resposta = self._servico.analisar(texto)
        salvou_com_dono = await self._registrar(
            RegistroAnalise.da_resposta(resposta, tipo_input="texto"), token_de_sessao
        )
        return resposta.model_copy(update={"salva_no_historico": salvou_com_dono})

    async def _registrar(self, registro: RegistroAnalise, token: str | None) -> bool:
        """Resolve o dono e grava, num teto só. Devolve se gravou ligada a uma conta.

        Falha ao registrar nunca derruba a análise (ADR-0012; filosofia das invariantes 3 e 4).
        Resolver a sessão e gravar dividem o mesmo `timeout_persistencia_s`: o orçamento da
        invariante 8 não ganha etapa nova, e o Neon acordando custa uma espera só (ADR-0015).

        O `except Exception` largo é intencional: banco fora, timeout e erro de integridade têm o
        mesmo destino. A transação é descartada pelo repositório. O log leva só o tipo da
        exceção — a mensagem de erro do driver pode citar valores da linha.
        """
        try:
            async with asyncio.timeout(self._timeout_s):
                usuario_id = await self._resolver_dono(token)
                await self._repositorio.registrar(
                    dataclasses.replace(registro, usuario_id=usuario_id)
                )
        except Exception as exc:
            logger.warning("Registro da análise descartado: %s", type(exc).__name__)
            return False
        return usuario_id is not None

    async def _resolver_dono(self, token: str | None) -> uuid.UUID | None:
        """Sessão válida → id da conta; sem cookie, inválida ou vencida → anônima.

        Erro na consulta também cai para anônima: a análise ainda é gravada, só sem dono. O
        timeout não passa por aqui — o cancelamento é `BaseException`, não `Exception`, e quem o
        trata é o `_registrar`, que então não grava nada.
        """
        if not token:
            return None
        try:
            usuario = await self._sessoes.buscar_usuario(hash_do_token(token))
        except Exception as exc:
            logger.warning(
                "Sessão não consultada; análise gravada sem dono: %s", type(exc).__name__
            )
            return None
        return usuario.id if usuario is not None else None
