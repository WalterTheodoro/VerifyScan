"""Cache e contador da reputação de links, no Postgres (ADR-0028).

Mesmo estilo do `repositorio_uso.py`: o limite é conferido e somado numa instrução só, para dois
pedidos simultâneos não passarem os dois.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Protocol, cast

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.reputacao import ReputacaoCache, ReputacaoUso
from app.reputation.tipos import ItemDeCache, Veredito
from app.schemas.analise import FonteReputacao

# O contador de um dia só serve naquele dia; guardar dois cobre a virada.
_USO_GUARDADO = timedelta(days=2)


def inicio_do_minuto(agora: datetime) -> datetime:
    return agora.astimezone(UTC).replace(second=0, microsecond=0)


def inicio_do_dia(agora: datetime) -> datetime:
    """O dia do limite é o de UTC. A documentação do VirusTotal não diz quando o limite diário
    zera; UTC é a suposição, registrada no ADR-0028."""
    return agora.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


class RepositorioReputacao(Protocol):
    async def buscar(
        self, fonte: FonteReputacao, chaves: Sequence[str], agora: datetime
    ) -> dict[str, Veredito]: ...

    async def guardar(self, itens: Sequence[ItemDeCache]) -> None: ...

    async def reservar(
        self, fonte: FonteReputacao, agora: datetime, consultas: int, por_minuto: int, por_dia: int
    ) -> bool: ...


class _LimiteAtingido(Exception):
    """Desfaz a transação da reserva: a soma do minuto não fica se a do dia não coube."""


class RepositorioReputacaoPostgres:
    def __init__(self, fabrica_de_sessoes: async_sessionmaker[AsyncSession]) -> None:
        self._fabrica_de_sessoes = fabrica_de_sessoes

    async def buscar(
        self, fonte: FonteReputacao, chaves: Sequence[str], agora: datetime
    ) -> dict[str, Veredito]:
        """Só o que ainda não venceu. Resposta vencida é como se não existisse."""
        if not chaves:
            return {}
        async with self._fabrica_de_sessoes() as sessao:
            linhas = await sessao.execute(
                select(ReputacaoCache.chave, ReputacaoCache.veredito).where(
                    ReputacaoCache.fonte == fonte,
                    ReputacaoCache.chave.in_(chaves),
                    ReputacaoCache.expira_em > agora,
                )
            )
            return {chave: cast(Veredito, veredito) for chave, veredito in linhas.all()}

    async def guardar(self, itens: Sequence[ItemDeCache]) -> None:
        """Grava ou substitui cada resposta e, na mesma transação, apaga o que venceu: a tabela
        se limpa no próprio uso, sem agendador."""
        if not itens:
            return
        agora = datetime.now(UTC)
        async with self._fabrica_de_sessoes() as sessao, sessao.begin():
            for item in itens:
                novo = insert(ReputacaoCache).values(
                    fonte=item.fonte,
                    chave=item.chave,
                    veredito=item.veredito,
                    expira_em=item.expira_em,
                )
                await sessao.execute(
                    novo.on_conflict_do_update(
                        index_elements=["fonte", "chave"],
                        set_={
                            "veredito": novo.excluded.veredito,
                            "expira_em": novo.excluded.expira_em,
                        },
                    )
                )
            await sessao.execute(delete(ReputacaoCache).where(ReputacaoCache.expira_em <= agora))
            await sessao.execute(
                delete(ReputacaoUso).where(ReputacaoUso.inicio < agora - _USO_GUARDADO)
            )

    async def reservar(
        self, fonte: FonteReputacao, agora: datetime, consultas: int, por_minuto: int, por_dia: int
    ) -> bool:
        """Soma `consultas` ao minuto e ao dia só se as duas somas couberem nos limites.

        Cada soma é um `INSERT … ON CONFLICT DO UPDATE … WHERE total <= limite`: a trava da linha
        faz o segundo pedido ver a soma do primeiro. As duas ficam na mesma transação; se o dia
        não couber, a do minuto é desfeita.
        """
        if consultas > min(por_minuto, por_dia):
            return False
        try:
            async with self._fabrica_de_sessoes() as sessao, sessao.begin():
                for janela, inicio, limite in (
                    ("minuto", inicio_do_minuto(agora), por_minuto),
                    ("dia", inicio_do_dia(agora), por_dia),
                ):
                    if not await self._somar(sessao, fonte, janela, inicio, consultas, limite):
                        raise _LimiteAtingido
        except _LimiteAtingido:
            return False
        return True

    @staticmethod
    async def _somar(
        sessao: AsyncSession,
        fonte: FonteReputacao,
        janela: str,
        inicio: datetime,
        consultas: int,
        limite: int,
    ) -> bool:
        tabela = ReputacaoUso.__table__
        novo = insert(ReputacaoUso).values(
            fonte=fonte, janela=janela, inicio=inicio, consultas=consultas
        )
        somar_ate_o_limite = novo.on_conflict_do_update(
            index_elements=["fonte", "janela", "inicio"],
            set_={"consultas": tabela.c.consultas + novo.excluded.consultas},
            where=tabela.c.consultas + novo.excluded.consultas <= limite,
        ).returning(tabela.c.consultas)
        return await sessao.scalar(somar_ate_o_limite) is not None
