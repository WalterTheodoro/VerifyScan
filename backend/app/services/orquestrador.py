"""Orquestração async da análise: motor → IA → regra fixa → registrar.

O `ServicoAnalise` continua síncrono e puro — é ele que o `avaliar_corpus` chama, sem banco e sem
IA. O I/O fica aqui, numa camada fina por cima, e a rota chama um método só.

O print (fatia 9, ADR-0023) entra por `analisar_print`: preparar a imagem → ler → e o MESMO miolo
do texto, sobre o que a pessoa recebeu. É o caminho que o corpus mede, e não um segundo caminho
sem medida.
"""

import asyncio
import dataclasses
import logging
import uuid

from app.analyzers.normalizacao import normalizar
from app.formulator.analisador import AnalisadorIA, ResultadoIA
from app.formulator.prompt import EntradaIA, PrintParaIA
from app.ocr.imagem import ImagemInvalida, preparar_imagem
from app.ocr.leitura import (
    LeitorDePrint,
    LeituraFalhou,
    texto_do_print,
    transcricao_marcada,
)
from app.schemas.analise import ContextoDoPrint, LeituraDoPrint, RespostaAnalise, TipoInput
from app.scoring.combinacao import combinar
from app.scoring.respostas import RespostasPadrao
from app.services.analise import EntradaInvalida, ServicoAnalise
from app.services.autenticacao import hash_do_token
from app.services.repositorio_analises import RegistroAnalise, RepositorioAnalises
from app.services.repositorio_sessoes import RepositorioSessoes

logger = logging.getLogger(__name__)

NAO_LEU = (
    "Não conseguimos ler o print. Tente um print mais nítido, ou copie e cole o texto da mensagem."
)
LEITURA_INDISPONIVEL = (
    "A leitura de prints não está disponível agora. Copie e cole o texto da mensagem."
)
SEM_MENSAGEM_RECEBIDA = (
    "Não encontramos no print uma mensagem que você recebeu. Envie o print com a mensagem "
    "suspeita, ou copie e cole o texto dela."
)


class LeituraIndisponivel(Exception):
    """A IA está desligada: sem ela, não há quem leia o print. A mensagem vai para a pessoa."""


class OrquestradorAnalise:
    def __init__(
        self,
        servico: ServicoAnalise,
        analisador_ia: AnalisadorIA,
        respostas: RespostasPadrao,
        repositorio: RepositorioAnalises,
        sessoes: RepositorioSessoes,
        timeout_s: float,
        leitor: LeitorDePrint | None = None,
        imagem_max_bytes: int = 5 * 1024 * 1024,
        timeout_ia_imagem_s: float = 10,
        maximo_de_caracteres: int = 5000,
    ) -> None:
        self._servico = servico
        self._analisador_ia = analisador_ia
        self._respostas = respostas
        self._repositorio = repositorio
        self._sessoes = sessoes
        self._timeout_s = timeout_s
        self._leitor = leitor or LeitorDePrint(None, timeout_s=10)
        self._imagem_max_bytes = imagem_max_bytes
        self._timeout_ia_imagem_s = timeout_ia_imagem_s
        self._maximo_de_caracteres = maximo_de_caracteres

    async def analisar(self, texto: str, token_de_sessao: str | None = None) -> RespostaAnalise:
        """`EntradaInvalida` propaga sem registrar: o que não foi analisado não pontuou.

        A análise não sabe quem é a pessoa; só o registro precisa saber (ADR-0015). Por isso o
        resultado sai antes de qualquer consulta à sessão, e o dono é resolvido dentro do teto
        do registro.
        """
        return await self._analisar(texto, token_de_sessao)

    async def analisar_print(
        self, imagem: bytes, texto_da_pessoa: str | None, token_de_sessao: str | None = None
    ) -> RespostaAnalise:
        """O print: `EntradaInvalida` (imagem recusada, leitura que falhou, sem mensagem recebida,
        texto demais) e `LeituraIndisponivel` propagam sem nível e sem registro.

        A imagem vive só nesta chamada, em memória (invariante 2). O motor analisa só o que a
        pessoa recebeu; o que ela mesma escreveu vai só para a IA (ADR-0023).
        """
        if not self._leitor.disponivel:
            raise LeituraIndisponivel(LEITURA_INDISPONIVEL)
        try:
            # Decodificar alguns megapixels é CPU: numa thread, para não travar o event loop.
            preparada = await asyncio.to_thread(preparar_imagem, imagem, self._imagem_max_bytes)
            leitura = await self._leitor.ler(preparada)
        except ImagemInvalida as erro:
            raise EntradaInvalida(str(erro)) from erro
        except LeituraFalhou as erro:
            raise EntradaInvalida(NAO_LEU) from erro
        texto_da_pessoa = (texto_da_pessoa or "").strip() or None
        marcada = transcricao_marcada(leitura.mensagens, texto_da_pessoa)
        if len(marcada) > self._maximo_de_caracteres:
            raise EntradaInvalida(
                f"O print tem mais texto do que conseguimos analisar de uma vez ({len(marcada)} "
                f"caracteres; o limite é {self._maximo_de_caracteres}). Recorte só a parte com a "
                "mensagem suspeita."
            )
        recebido = texto_do_print(leitura.mensagens)
        if not any(caractere.isalnum() for caractere in normalizar(recebido)):
            raise EntradaInvalida(SEM_MENSAGEM_RECEBIDA)
        resposta = await self._analisar(
            recebido,
            token_de_sessao,
            tipo_input="imagem",
            dados_do_print=PrintParaIA(
                mensagens=leitura.mensagens,
                contexto=leitura.contexto,
                texto_da_pessoa=texto_da_pessoa,
            ),
            texto_guardado=marcada,
        )
        return resposta.model_copy(
            update={
                "leitura_do_print": LeituraDoPrint(
                    mensagens=list(leitura.mensagens),
                    contexto=leitura.contexto,
                    texto_da_pessoa=texto_da_pessoa,
                )
            }
        )

    async def _analisar(
        self,
        texto: str,
        token_de_sessao: str | None,
        *,
        tipo_input: TipoInput = "texto",
        dados_do_print: PrintParaIA | None = None,
        texto_guardado: str | None = None,
    ) -> RespostaAnalise:
        """O miolo comum: motor → IA → regra fixa → registrar. `texto` é o que o motor analisa;
        `texto_guardado`, o que fica no histórico de quem tem conta (num print, a transcrição
        inteira, com quem mandou cada mensagem)."""
        resposta = self._servico.analisar(texto)
        resultado_ia = await self._analisador_ia.avaliar(
            EntradaIA(
                mensagem=texto,
                nivel_motor=resposta.nivel_motor,
                fatores=tuple(resposta.fatores),
                links=tuple(resposta.links),
                print=dados_do_print,
            ),
            timeout_s=self._timeout_ia_imagem_s if dados_do_print is not None else None,
        )
        if resultado_ia is not None:
            resposta = self._com_ia(resposta, resultado_ia)
        registro = await self._registrar(
            RegistroAnalise.da_resposta(
                resposta,
                tipo_input=tipo_input,
                ia_modelo=resultado_ia.modelo if resultado_ia is not None else None,
            ),
            token_de_sessao,
            texto_guardado or texto,
            resposta,
            dados_do_print.contexto if dados_do_print is not None else None,
        )
        return resposta.model_copy(
            update={
                "salva_no_historico": registro is not None and registro.usuario_id is not None,
                "texto_salvo": registro is not None and registro.texto_input is not None,
            }
        )

    def _com_ia(self, resposta: RespostaAnalise, resultado: ResultadoIA) -> RespostaAnalise:
        """A regra fixa decide: o nível final é o maior dos dois (ADR-0020). A IA pode subir o
        nível, nunca baixar; a orientação fixa acompanha o nível final.

        O nível da IA entra mesmo quando a explicação dela foi descartada: aí a tela mostra o
        plano B do nível final, e `nivel_ia` preenchido com `explicacao_indisponivel` diz isso.
        """
        nivel_final = combinar(resposta.nivel_motor, resultado.nivel_sugerido)
        return resposta.model_copy(
            update={
                "nivel_risco": nivel_final,
                "nivel_ia": resultado.nivel_sugerido,
                "orientacao": self._respostas.para(nivel_final),
                "explicacao_ia": resultado.explicacao,
                "explicacao_indisponivel": resultado.explicacao is None,
            }
        )

    async def _registrar(
        self,
        registro: RegistroAnalise,
        token: str | None,
        texto: str,
        resposta: RespostaAnalise,
        contexto_print: ContextoDoPrint | None = None,
    ) -> RegistroAnalise | None:
        """Resolve o dono e grava, num teto só. Devolve o que foi gravado, ou `None`.

        Com dono, a mensagem, a explicação da IA e o contexto do print vão junto (ADR-0018,
        ADR-0020, ADR-0023); sem dono, nunca (ADR-0006).

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
                    contexto_print=contexto_print if com_dono else None,
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
