"""Orquestração async da análise: motor → cota → IA → regra fixa → registrar.

O `ServicoAnalise` continua síncrono e puro — é ele que o `avaliar_corpus` chama, sem banco e sem
IA. O I/O fica aqui, numa camada fina por cima, e a rota chama um método só.

O print (fatia 9, ADR-0023) entra por `analisar_print`: preparar a imagem → ler → e o MESMO miolo
do texto, sobre o que a pessoa recebeu. É o caminho que o corpus mede, e não um segundo caminho
sem medida.

A cota da IA (fatia 10, ADR-0024) abre uma janela antes da IA: resolve quem é a pessoa e reserva
as unidades, num teto só (`timeout_cota_s`). Isso muda a ordem do ADR-0015 — o dono só era
conhecido no registro —, mas a análise continua sem depender da conta: sem a janela, o texto sai
só com o motor, nunca com erro.
"""

import asyncio
import dataclasses
import logging
import uuid
from dataclasses import dataclass
from datetime import date

from app.analyzers.normalizacao import normalizar
from app.core.ip import IP_DESCONHECIDO
from app.formulator.analisador import AnalisadorIA, ResultadoIA
from app.formulator.cliente import ConsumoDaIA
from app.formulator.prompt import EntradaIA, PrintParaIA
from app.models.uso import chave_da_conta, chave_do_ip
from app.ocr.imagem import ImagemInvalida, ImagemPreparada, preparar_imagem
from app.ocr.leitura import (
    LeitorDePrint,
    LeituraFalhou,
    texto_do_print,
    transcricao_marcada,
)
from app.schemas.analise import (
    ContextoDoPrint,
    LeituraDoPrint,
    MensagemDoPrint,
    RespostaAnalise,
    TipoInput,
)
from app.scoring.combinacao import combinar
from app.scoring.respostas import RespostasPadrao
from app.services.analise import EntradaInvalida, ServicoAnalise
from app.services.autenticacao import hash_do_token
from app.services.cota import (
    COTA_COM_CONTA,
    COTA_DE_PRINT,
    COTA_DE_TEXTO,
    UNIDADES_PRINT,
    UNIDADES_TEXTO,
    ServicoCota,
    SituacaoCota,
)
from app.services.repositorio_analises import RegistroAnalise, RepositorioAnalises
from app.services.repositorio_sessoes import RepositorioSessoes

logger = logging.getLogger(__name__)

# Uma frase só para os dois casos que a leitura não separa com segurança: print borrado e imagem
# que não é conversa (correção 9.1). "Mais nítido" não ajuda quem mandou a foto de um boleto.
NAO_LEU = (
    "Não conseguimos ler uma conversa nesta imagem. Envie um print da mensagem, ou copie e cole o "
    "texto."
)
LEITURA_INDISPONIVEL = (
    "A leitura de prints não está disponível agora. Copie e cole o texto da mensagem."
)
SEM_MENSAGEM_RECEBIDA = (
    "Não encontramos no print uma mensagem que você recebeu. Envie o print com a mensagem "
    "suspeita, ou copie e cole o texto dela."
)


class LeituraIndisponivel(Exception):
    """A IA está desligada, ou a cota não pôde ser conferida: sem as duas, o print não é lido. A
    mensagem vai para a pessoa."""


class CotaEsgotada(Exception):
    """O print não cabe na cota de hoje, ou o teto global foi atingido. Sem leitura não há print:
    vira 429, com a frase que manda colar o texto, que ainda pode ser analisado (ADR-0024)."""


@dataclass(frozen=True)
class JanelaDaCota:
    """O que a janela da cota apurou antes da IA.

    `dono_resolvido` diz se a sessão chegou a ser consultada: se a janela estourou antes, o
    registro consulta de novo, no teto dele. `situacao=None` é a cota que não pôde ser conferida
    (banco fora ou lento): fail-closed para o dinheiro — o texto sai sem IA, o print não sai.
    """

    dia: date
    dono_resolvido: bool
    usuario_id: uuid.UUID | None
    situacao: SituacaoCota | None


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
        cota: ServicoCota | None = None,
        consumo: ConsumoDaIA | None = None,
        timeout_cota_s: float = 1.5,
    ) -> None:
        """`cota=None`: sem limite de uso (os testes que não tratam de cota). `consumo` é o mesmo
        objeto que o analisador e o leitor desta requisição preenchem com o usage (ADR-0024)."""
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
        self._cota = cota
        self._consumo = consumo
        self._timeout_cota_s = timeout_cota_s

    async def analisar(
        self, texto: str, token_de_sessao: str | None = None, chave_ip: str | None = None
    ) -> RespostaAnalise:
        """`EntradaInvalida` propaga sem registrar e sem gastar cota: o que não foi analisado não
        pontuou. `chave_ip` é o HMAC do IP, a chave da cota de quem não tem conta (ADR-0024).
        """
        return await self._analisar(texto, token_de_sessao, chave_ip)

    async def analisar_print(
        self,
        imagem: bytes,
        texto_da_pessoa: str | None,
        token_de_sessao: str | None = None,
        chave_ip: str | None = None,
    ) -> RespostaAnalise:
        """O print: `EntradaInvalida` (imagem recusada, leitura que falhou, sem mensagem recebida,
        texto demais), `LeituraIndisponivel` e `CotaEsgotada` propagam sem nível e sem registro.

        A imagem vive só nesta chamada, em memória (invariante 2). O motor analisa só o que a
        pessoa recebeu; o que ela mesma escreveu vai só para a IA (ADR-0023).

        A cota é reservada depois de conferir a imagem (imagem inválida não gasta unidade) e antes
        de ler (a leitura é cobrada). As 3 unidades cobrem a leitura e a análise.
        """
        if not self._leitor.disponivel:
            raise LeituraIndisponivel(LEITURA_INDISPONIVEL)
        try:
            # Decodificar alguns megapixels é CPU: numa thread, para não travar o event loop.
            preparada = await asyncio.to_thread(preparar_imagem, imagem, self._imagem_max_bytes)
        except ImagemInvalida as erro:
            raise EntradaInvalida(str(erro)) from erro
        janela = await self._abrir_janela(token_de_sessao, chave_ip, UNIDADES_PRINT)
        if janela is not None:
            if janela.situacao is None:
                raise LeituraIndisponivel(LEITURA_INDISPONIVEL)
            if not janela.situacao.concedida:
                raise CotaEsgotada(COTA_DE_PRINT)
        try:
            return await self._ler_e_analisar(
                preparada, texto_da_pessoa, token_de_sessao, chave_ip, janela
            )
        finally:
            # A leitura que falhou também foi cobrada. No caminho feliz, o miolo já gravou o gasto
            # em paralelo com o registro e zerou o consumo: aqui não sobra nada a gravar.
            if janela is not None:
                await self._registrar_gasto(janela.dia)

    async def _ler_e_analisar(
        self,
        preparada: ImagemPreparada,
        texto_da_pessoa: str | None,
        token_de_sessao: str | None,
        chave_ip: str | None,
        janela: JanelaDaCota | None,
    ) -> RespostaAnalise:
        try:
            leitura = await self._leitor.ler(preparada)
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
            chave_ip,
            janela=janela,
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
                    mensagens_para_exibir=[
                        MensagemDoPrint(de=m.de, texto=self._servico.para_exibir(m.texto))
                        for m in leitura.mensagens
                    ],
                    contexto=leitura.contexto,
                    texto_da_pessoa=texto_da_pessoa,
                )
            }
        )

    async def _analisar(
        self,
        texto: str,
        token_de_sessao: str | None,
        chave_ip: str | None,
        *,
        janela: JanelaDaCota | None = None,
        tipo_input: TipoInput = "texto",
        dados_do_print: PrintParaIA | None = None,
        texto_guardado: str | None = None,
    ) -> RespostaAnalise:
        """O miolo comum: motor → cota → IA → regra fixa → registrar. `texto` é o que o motor
        analisa; `texto_guardado`, o que fica no histórico de quem tem conta (num print, a
        transcrição inteira, com quem mandou cada mensagem).

        No texto, a janela da cota abre aqui, depois do motor: a entrada inválida já saiu com
        `EntradaInvalida` e não gastou unidade. No print, ela chega pronta.
        """
        resposta = self._servico.analisar(texto)
        if dados_do_print is None:
            janela = await self._abrir_janela(token_de_sessao, chave_ip, UNIDADES_TEXTO)
        resultado_ia: ResultadoIA | None = None
        if janela is None or (janela.situacao is not None and janela.situacao.concedida):
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
        if janela is not None:
            resposta = self._com_cota(resposta, janela)
        # O gasto vai em paralelo com o registro, cada um no próprio teto: a invariante 8 não
        # ganha etapa nova no fim da análise.
        registro, _ = await asyncio.gather(
            self._registrar(
                RegistroAnalise.da_resposta(
                    resposta,
                    tipo_input=tipo_input,
                    ia_modelo=resultado_ia.modelo if resultado_ia is not None else None,
                ),
                token_de_sessao,
                texto_guardado or texto,
                resposta,
                dados_do_print.contexto if dados_do_print is not None else None,
                janela,
            ),
            self._registrar_gasto(janela.dia if janela is not None else None),
        )
        return resposta.model_copy(
            update={
                "salva_no_historico": registro is not None and registro.usuario_id is not None,
                "texto_salvo": registro is not None and registro.texto_input is not None,
            }
        )

    async def _abrir_janela(
        self, token: str | None, chave_ip: str | None, unidades: int
    ) -> JanelaDaCota | None:
        """Resolve o dono e reserva `unidades`, num teto só. `None` quando não há cota a conferir:
        sem `ServicoCota`, ou com a IA desligada, que não custa nada.

        O `except Exception` largo é intencional, como no registro: banco fora e timeout têm o
        mesmo destino, a cota não conferida. O log leva só o tipo da exceção.
        """
        if self._cota is None or not self._analisador_ia.disponivel:
            return None
        dia = self._cota.hoje()
        resolvido = False
        usuario_id: uuid.UUID | None = None
        try:
            async with asyncio.timeout(self._timeout_cota_s):
                usuario_id = await self._resolver_dono(token)
                resolvido = True
                chave = (
                    chave_da_conta(usuario_id)
                    if usuario_id is not None
                    else chave_do_ip(chave_ip or IP_DESCONHECIDO)
                )
                situacao = await self._cota.reservar_ia(
                    chave, usuario_id is not None, unidades, dia
                )
        except Exception as exc:
            logger.warning("Cota da IA não conferida, análise sem IA: %s", type(exc).__name__)
            return JanelaDaCota(dia, resolvido, usuario_id, situacao=None)
        return JanelaDaCota(dia, dono_resolvido=True, usuario_id=usuario_id, situacao=situacao)

    def _com_cota(self, resposta: RespostaAnalise, janela: JanelaDaCota) -> RespostaAnalise:
        """Quanto resta e, se a cota negou a IA, o porquê. Cota não conferida não é cota: sai o
        plano B de sempre, sem frase de cota e sem o "restam"."""
        if janela.situacao is None or self._cota is None:
            return resposta
        atualizacao: dict[str, object] = {"ia_restantes_hoje": janela.situacao.restantes}
        if not janela.situacao.concedida:
            aviso = COTA_DE_TEXTO
            if janela.usuario_id is None:
                aviso += " " + COTA_COM_CONTA.format(cota=self._cota.cota_com_conta)
            atualizacao |= {"motivo_sem_ia": "cota", "aviso_sem_ia": aviso}
        return resposta.model_copy(update=atualizacao)

    async def _registrar_gasto(self, dia: date | None) -> None:
        """Grava o consumo desta requisição e o zera: chamado de novo (o `finally` do print), não
        soma duas vezes. Nunca levanta."""
        if self._cota is None or self._consumo is None or dia is None or self._consumo.vazio:
            return
        consumo = dataclasses.replace(self._consumo)
        self._consumo.zerar()
        await self._cota.registrar_gasto(consumo, dia, self._timeout_s)

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
        janela: JanelaDaCota | None = None,
    ) -> RegistroAnalise | None:
        """Resolve o dono e grava, num teto só. Devolve o que foi gravado, ou `None`.

        Com dono, a mensagem, a explicação da IA e o contexto do print vão junto (ADR-0018,
        ADR-0020, ADR-0023); sem dono, nunca (ADR-0006).

        Falha ao registrar nunca derruba a análise (ADR-0012; filosofia das invariantes 3 e 4).
        Resolver a sessão e gravar dividem o mesmo `timeout_persistencia_s` (ADR-0015). Se a
        janela da cota já resolveu o dono, ele é reaproveitado, sem segunda consulta.

        O `except Exception` largo é intencional: banco fora, timeout e erro de integridade têm o
        mesmo destino. A transação é descartada pelo repositório. O log leva só o tipo da
        exceção — a mensagem de erro do driver pode citar valores da linha.
        """
        try:
            async with asyncio.timeout(self._timeout_s):
                usuario_id = (
                    janela.usuario_id
                    if janela is not None and janela.dono_resolvido
                    else await self._resolver_dono(token)
                )
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
        trata é quem abriu o teto (`_registrar` ou `_abrir_janela`).
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
