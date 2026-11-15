"""Cota diária da IA, teto global de gasto e limite de cadastros por IP (fatia 10, ADR-0024).

Cada análise com IA gasta unidades da cota do dia: texto 1, print 3. A chave é a conta, para quem
entrou, ou o HMAC do IP, para quem não entrou. O dia vira à meia-noite de São Paulo.

Por cima das cotas, um teto de gasto de todo mundo somado, calculado pelo usage que a API devolveu
e pelos preços do `Settings`. Atingido, ninguém tem IA até a meia-noite — com a mesma frase da
cota, sem dizer que é um teto global.

A conta é reservada ANTES da chamada à IA, e as unidades não voltam se a IA cair no plano B: a
devolução exigiria uma segunda escrita no fim da análise, e a chamada que falhou pode ter sido
cobrada do mesmo jeito.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.core.relogio import Relogio, dia_de_sao_paulo
from app.formulator.cliente import ConsumoDaIA
from app.models.uso import chave_do_ip
from app.services.repositorio_uso import GastoDaChamada, RepositorioUso

logger = logging.getLogger(__name__)

# Proporção do custo medido na fatia 9: US$ 0,00126 por print (leitura + análise) contra
# US$ 0,00043 por texto, quase 3 vezes (ADR-0023). Não é peso de risco: não mora no `regras.yaml`.
UNIDADES_TEXTO = 1
UNIDADES_PRINT = 3

COTA_DE_TEXTO = (
    "Você usou as análises com IA de hoje. Esta foi feita só com as regras automáticas, que podem "
    "deixar passar golpes mais elaborados."
)
COTA_COM_CONTA = "Com uma conta, são {cota} por dia."
COTA_DE_PRINT = (
    "Você atingiu o limite de prints de hoje. Copie e cole o texto da mensagem, que ainda pode ser "
    "analisado."
)

_MILHAO = Decimal(1_000_000)


@dataclass(frozen=True)
class SituacaoCota:
    """`restantes`: unidades que sobram hoje para esta chave (0 com o teto global atingido)."""

    concedida: bool
    restantes: int


class ServicoCota:
    def __init__(
        self,
        uso: RepositorioUso,
        relogio: Relogio,
        *,
        cota_sem_conta: int,
        cota_com_conta: int,
        teto_usd: Decimal,
        preco_entrada_por_milhao: Decimal,
        preco_saida_por_milhao: Decimal,
        cadastros_por_ip: int,
    ) -> None:
        self._uso = uso
        self._relogio = relogio
        self._cota_sem_conta = cota_sem_conta
        self._cota_com_conta = cota_com_conta
        self._teto_usd = teto_usd
        self._preco_entrada = preco_entrada_por_milhao
        self._preco_saida = preco_saida_por_milhao
        self._cadastros_por_ip = cadastros_por_ip

    @property
    def cota_com_conta(self) -> int:
        return self._cota_com_conta

    def hoje(self) -> date:
        """O dia da cota. Calculado uma vez por requisição: reserva e gasto usam o mesmo, mesmo
        que a análise atravesse a meia-noite."""
        return dia_de_sao_paulo(self._relogio())

    async def reservar_ia(
        self, chave: str, com_conta: bool, unidades: int, dia: date
    ) -> SituacaoCota:
        """Confere o teto global e reserva as unidades. Erro do banco propaga: quem chama decide
        (o texto sai sem IA; o print, 503)."""
        if await self._uso.gasto_do_dia(dia) >= self._teto_usd:
            return SituacaoCota(concedida=False, restantes=0)
        limite = self._cota_com_conta if com_conta else self._cota_sem_conta
        reserva = await self._uso.reservar("ia", chave, dia, unidades, limite)
        return SituacaoCota(concedida=reserva.concedida, restantes=max(0, limite - reserva.usadas))

    async def reservar_cadastro(self, hmac_do_ip: str) -> bool:
        """Uma conta nova a mais para este IP hoje, se couber. Erro do banco propaga."""
        reserva = await self._uso.reservar(
            "cadastro", chave_do_ip(hmac_do_ip), self.hoje(), 1, self._cadastros_por_ip
        )
        return reserva.concedida

    def custo(self, consumo: ConsumoDaIA) -> Decimal:
        return (
            consumo.tokens_entrada * self._preco_entrada + consumo.tokens_saida * self._preco_saida
        ) / _MILHAO

    async def registrar_gasto(self, consumo: ConsumoDaIA, dia: date, timeout_s: float) -> None:
        """Soma o consumo da requisição ao dia e avisa, uma vez por dia, quando o teto é atingido.
        Nunca levanta.

        O `except Exception` largo é intencional, como no registro da análise (ADR-0012): o gasto
        que não foi gravado não pode derrubar uma análise que já saiu. O log leva só o tipo da
        exceção.
        """
        if consumo.vazio:
            return
        gasto = GastoDaChamada(
            tokens_entrada=consumo.tokens_entrada,
            tokens_saida=consumo.tokens_saida,
            custo_usd=self.custo(consumo),
            chamadas=consumo.chamadas,
            chamadas_com_timeout=consumo.timeouts,
        )
        try:
            async with asyncio.timeout(timeout_s):
                total = await self._uso.somar_gasto(dia, gasto)
                if total >= self._teto_usd and await self._uso.marcar_teto_avisado(
                    dia, self._teto_usd
                ):
                    logger.warning(
                        "Teto diário de gasto com a IA atingido (US$ %s): as análises seguem só "
                        "com o motor até a meia-noite",
                        self._teto_usd,
                    )
        except Exception as exc:
            logger.warning("Gasto da IA não registrado: %s", type(exc).__name__)
