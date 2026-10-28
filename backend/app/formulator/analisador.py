"""`AnalisadorIA` — a etapa da IA no pipeline: uma chamada, um teto, e plano B em qualquer falha.

A análise nunca falha por causa da IA (invariante 3). Desligada, lenta, fora do ar, recusando,
cortada ou respondendo algo inválido: o resultado é `None`, e o orquestrador responde só com o
motor (ADR-0020).
"""

import asyncio
import logging
import time
from dataclasses import dataclass

from app.formulator.cliente import ClienteIA, RespostaIA
from app.formulator.prompt import EntradaIA, montar_entrada
from app.formulator.saida import SaidaIA, SaidaInutilizavel, explicacao_da_saida
from app.schemas.analise import ExplicacaoIA, NivelRisco

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResultadoIA:
    """O que a IA acrescenta: um nível sugerido e a explicação, já limpa.

    `explicacao=None` quando ela não cumpriu o mínimo depois da limpeza: a tela usa o plano B do
    nível final, mas o nível sugerido continua valendo (ADR-0020).
    """

    nivel_sugerido: NivelRisco
    explicacao: ExplicacaoIA | None
    modelo: str


class SaidaRecusada(Exception):
    """O modelo recusou responder (`stop_reason: refusal`)."""


class SaidaCortada(Exception):
    """A resposta bateu no `max_tokens`: o JSON pode estar pela metade."""


class ParadaInesperada(Exception):
    """A resposta parou por um motivo que não é o fim normal."""


class AnalisadorIA:
    def __init__(self, cliente: ClienteIA | None, timeout_s: float) -> None:
        """`cliente=None` é a IA desligada (`IA_ATIVADA=false`)."""
        self._cliente = cliente
        self._timeout_s = timeout_s

    async def avaliar(
        self, entrada: EntradaIA, timeout_s: float | None = None
    ) -> ResultadoIA | None:
        """O resultado da IA, ou `None` para o plano B.

        `timeout_s` troca o teto desta chamada: o caminho de imagem usa um menor, porque a leitura
        já gastou parte do orçamento da invariante 8 (ADR-0023).

        O `except Exception` largo é intencional: todas as falhas têm o mesmo destino. O log leva
        só o tipo da exceção e a latência, nunca o texto dela, da mensagem ou da resposta — a
        resposta pode citar a mensagem, e o erro pode ter vindo do servidor.
        """
        if self._cliente is None:
            return None
        inicio = time.perf_counter()
        try:
            async with asyncio.timeout(timeout_s or self._timeout_s):
                resposta = await self._cliente.gerar(entrada.sistema, montar_entrada(entrada))
            resultado = _interpretar(resposta)
        except Exception as exc:
            logger.warning(
                "Análise com IA indisponível, resposta só do motor: %s em %d ms",
                type(exc).__name__,
                _ms_desde(inicio),
            )
            return None
        logger.info(
            "Análise com IA em %d ms: %d tokens de entrada, %d de saída",
            _ms_desde(inicio),
            resposta.tokens_entrada,
            resposta.tokens_saida,
        )
        return resultado


def _interpretar(resposta: RespostaIA) -> ResultadoIA:
    """Só falha de FORMA levanta — e descarta a IA inteira: recusa, corte, parada inesperada,
    JSON inválido ou nível fora do enum. Falha de TEXTO descarta só a explicação."""
    if resposta.motivo_parada == "refusal":
        raise SaidaRecusada
    if resposta.motivo_parada == "max_tokens":
        raise SaidaCortada
    if resposta.motivo_parada != "end_turn":
        raise ParadaInesperada
    saida = SaidaIA.model_validate_json(resposta.texto)
    explicacao: ExplicacaoIA | None
    try:
        explicacao = explicacao_da_saida(saida)
    except SaidaInutilizavel as exc:
        logger.warning("Explicação da IA descartada, nível da IA mantido: %s", type(exc).__name__)
        explicacao = None
    return ResultadoIA(
        nivel_sugerido=saida.nivel_sugerido, explicacao=explicacao, modelo=resposta.modelo
    )


def _ms_desde(inicio: float) -> int:
    return round((time.perf_counter() - inicio) * 1000)
