"""Orquestração async da análise: motor → IA → regra fixa → registrar.

O `ServicoAnalise` continua síncrono e puro — é ele que o `avaliar_corpus` chama, sem banco e sem
IA. O I/O fica aqui, numa camada fina por cima, e a rota chama um método só.
"""

import asyncio
import dataclasses
import logging
import uuid

from app.formulator.analisador import AnalisadorIA, ResultadoIA
from app.formulator.prompt import EntradaIA
from app.schemas.analise import RespostaAnalise
from app.scoring.combinacao import combinar
from app.scoring.respostas import RespostasPadrao
from app.services.analise import ServicoAnalise
from app.services.autenticacao import hash_do_token
from app.services.repositorio_analises import RegistroAnalise, RepositorioAnalises
from app.services.repositorio_sessoes import RepositorioSessoes

logger = logging.getLogger(__name__)


class OrquestradorAnalise:
    def __init__(
        self,
        servico: ServicoAnalise,
        analisador_ia: AnalisadorIA,
        respostas: RespostasPadrao,
        repositorio: RepositorioAnalises,
        sessoes: RepositorioSessoes,
        timeout_s: float,
    ) -> None:
        self._servico = servico
        self._analisador_ia = analisador_ia
        self._respostas = respostas
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
        resultado_ia = await self._analisador_ia.avaliar(
            EntradaIA(
                mensagem=texto,
                nivel_motor=resposta.nivel_motor,
                fatores=tuple(resposta.fatores),
                urls=tuple(resposta.urls_analisadas),
            )
        )
        if resultado_ia is not None:
            resposta = self._com_ia(resposta, resultado_ia)
        registro = await self._registrar(
            RegistroAnalise.da_resposta(
                resposta,
                tipo_input="texto",
                ia_modelo=resultado_ia.modelo if resultado_ia is not None else None,
            ),
            token_de_sessao,
            texto,
            resposta,
        )
        return resposta.model_copy(
            update={
                "salva_no_historico": registro is not None and registro.usuario_id is not None,
                "texto_salvo": registro is not None and registro.texto_input is not None,
            }
        )

    def _com_ia(self, resposta: RespostaAnalise, resultado: ResultadoIA) -> RespostaAnalise:
        """A regra fixa decide: o nível final é o maior dos dois (ADR-0020). A IA pode subir o
        nível, nunca baixar; a orientação fixa acompanha o nível final."""
        nivel_final = combinar(resposta.nivel_motor, resultado.nivel_sugerido)
        return resposta.model_copy(
            update={
                "nivel_risco": nivel_final,
                "nivel_ia": resultado.nivel_sugerido,
                "orientacao": self._respostas.para(nivel_final),
                "explicacao_ia": resultado.explicacao,
                "explicacao_indisponivel": False,
            }
        )

    async def _registrar(
        self,
        registro: RegistroAnalise,
        token: str | None,
        texto: str,
        resposta: RespostaAnalise,
    ) -> RegistroAnalise | None:
        """Resolve o dono e grava, num teto só. Devolve o que foi gravado, ou `None`.

        Com dono, a mensagem e a explicação da IA vão junto (ADR-0018, ADR-0020); sem dono,
        nunca (ADR-0006).

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
                com_dono = usuario_id is not None
                registro = dataclasses.replace(
                    registro,
                    usuario_id=usuario_id,
                    texto_input=texto if com_dono else None,
                    explicacao_ia=resposta.explicacao_ia if com_dono else None,
                )
                await self._repositorio.registrar(registro)
        except Exception as exc:
            logger.warning("Registro da análise descartado: %s", type(exc).__name__)
            return None
        return registro

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
