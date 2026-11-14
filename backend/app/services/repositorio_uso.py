"""Uso diário e gasto da IA no banco (fatia 10, ADR-0024): um Protocol, a implementação real e
um falso em memória nos testes, como os outros repositórios.

O dia vem de fora, já calculado no fuso de São Paulo pelo serviço — e não do `now()` do banco,
como nas sessões: o dia da cota precisa de relógio injetável no teste, e o fuso é regra do
produto, não do servidor.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import GastoDiarioIA, UsoDiario
from app.models.uso import Finalidade


@dataclass(frozen=True)
class Reserva:
    """`usadas`: o total do dia depois da reserva, se concedida; o de antes, se negada."""

    concedida: bool
    usadas: int


@dataclass(frozen=True)
class GastoDaChamada:
    tokens_entrada: int
    tokens_saida: int
    custo_usd: Decimal
    chamadas: int
    chamadas_com_timeout: int


class RepositorioUso(Protocol):
    async def reservar(
        self, finalidade: Finalidade, chave: str, dia: date, unidades: int, limite: int
    ) -> Reserva: ...

    async def gasto_do_dia(self, dia: date) -> Decimal: ...

    async def somar_gasto(self, dia: date, gasto: GastoDaChamada) -> Decimal: ...

    async def marcar_teto_avisado(self, dia: date, teto: Decimal) -> bool: ...

    async def apagar_antigos(self, antes_de: date) -> int: ...


class RepositorioUsoPostgres:
    def __init__(self, fabrica_de_sessoes: async_sessionmaker[AsyncSession]) -> None:
        self._fabrica_de_sessoes = fabrica_de_sessoes

    async def reservar(
        self, finalidade: Finalidade, chave: str, dia: date, unidades: int, limite: int
    ) -> Reserva:
        """Soma `unidades` ao dia da chave só se o total não passar de `limite`, numa instrução.

        Ler, conferir e gravar em três passos deixaria dois pedidos simultâneos lerem o mesmo
        total e passarem os dois. Aqui, o `ON CONFLICT` trava a linha: o segundo pedido espera o
        primeiro e já vê a soma dele no `WHERE`. Sem linha de volta, a reserva foi negada, e uma
        leitura diz quanto já foi usado.
        """
        if unidades > limite:
            return Reserva(concedida=False, usadas=await self._usadas(finalidade, chave, dia))
        tabela = UsoDiario.__table__
        novo = insert(UsoDiario).values(
            finalidade=finalidade, chave=chave, dia=dia, unidades=unidades
        )
        somar_ate_o_limite = novo.on_conflict_do_update(
            index_elements=["finalidade", "chave", "dia"],
            set_={"unidades": tabela.c.unidades + novo.excluded.unidades},
            where=tabela.c.unidades + novo.excluded.unidades <= limite,
        ).returning(tabela.c.unidades)
        async with self._fabrica_de_sessoes() as sessao, sessao.begin():
            usadas = await sessao.scalar(somar_ate_o_limite)
        if usadas is not None:
            return Reserva(concedida=True, usadas=usadas)
        return Reserva(concedida=False, usadas=await self._usadas(finalidade, chave, dia))

    async def _usadas(self, finalidade: Finalidade, chave: str, dia: date) -> int:
        async with self._fabrica_de_sessoes() as sessao:
            usadas = await sessao.scalar(
                select(UsoDiario.unidades).where(
                    UsoDiario.finalidade == finalidade,
                    UsoDiario.chave == chave,
                    UsoDiario.dia == dia,
                )
            )
        return usadas or 0

    async def gasto_do_dia(self, dia: date) -> Decimal:
        async with self._fabrica_de_sessoes() as sessao:
            custo = await sessao.scalar(
                select(GastoDiarioIA.custo_usd).where(GastoDiarioIA.dia == dia)
            )
        return custo if custo is not None else Decimal(0)

    async def somar_gasto(self, dia: date, gasto: GastoDaChamada) -> Decimal:
        """Soma ao dia, numa instrução (o mesmo UPSERT da cota), e devolve o custo total."""
        tabela = GastoDiarioIA.__table__
        novo = insert(GastoDiarioIA).values(
            dia=dia,
            tokens_entrada=gasto.tokens_entrada,
            tokens_saida=gasto.tokens_saida,
            custo_usd=gasto.custo_usd,
            chamadas=gasto.chamadas,
            chamadas_com_timeout=gasto.chamadas_com_timeout,
        )
        somar = {
            coluna: tabela.c[coluna] + novo.excluded[coluna]
            for coluna in (
                "tokens_entrada",
                "tokens_saida",
                "custo_usd",
                "chamadas",
                "chamadas_com_timeout",
            )
        }
        somar_ao_dia = novo.on_conflict_do_update(index_elements=["dia"], set_=somar).returning(
            tabela.c.custo_usd
        )
        async with self._fabrica_de_sessoes() as sessao, sessao.begin():
            total = await sessao.scalar(somar_ao_dia)
        return total if total is not None else Decimal(0)

    async def marcar_teto_avisado(self, dia: date, teto: Decimal) -> bool:
        """Verdadeiro só para o primeiro pedido que encontra o teto atingido e ainda não avisado.

        É o banco que garante o "uma vez por dia": uma marca em memória voltaria a avisar depois
        de cada sono do Render.
        """
        async with self._fabrica_de_sessoes() as sessao, sessao.begin():
            marcado = await sessao.scalar(
                update(GastoDiarioIA)
                .where(
                    GastoDiarioIA.dia == dia,
                    GastoDiarioIA.custo_usd >= teto,
                    GastoDiarioIA.teto_avisado.is_(False),
                )
                .values(teto_avisado=True)
                .returning(GastoDiarioIA.dia)
            )
        return marcado is not None

    async def apagar_antigos(self, antes_de: date) -> int:
        """Apaga o uso de dias anteriores a `antes_de`.

        Só o uso, que é dado pessoal pseudonimizado. O gasto fica: é um total do dia, sem pessoa,
        e é a série que mede o custo e as chamadas com timeout ao longo do tempo (uma linha por
        dia).
        """
        async with self._fabrica_de_sessoes() as sessao, sessao.begin():
            apagados = await sessao.scalars(
                delete(UsoDiario).where(UsoDiario.dia < antes_de).returning(UsoDiario.dia)
            )
            return len(apagados.all())
