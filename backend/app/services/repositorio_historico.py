"""Histórico da conta no banco (ADR-0015) — o padrão dos outros repositórios: Protocol,
implementação Postgres e falso em memória nos testes.

A hora é sempre a do banco (`now()`), como no ADR-0012: a janela não depende do relógio do
processo. Nada aqui lê ou devolve texto de mensagem — a tabela não tem onde guardá-lo.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, cast

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import func

from app.models import Analise
from app.schemas.analise import NivelRisco


@dataclass(frozen=True)
class FatorDoHistorico:
    categoria: str
    descricao: str
    peso: int


@dataclass(frozen=True)
class AnaliseDoHistorico:
    """O que a pessoa reconhece de uma consulta passada: quando, que nível e por quê."""

    id: uuid.UUID
    criada_em: datetime
    nivel_risco: NivelRisco
    score: int
    fatores: tuple[FatorDoHistorico, ...]


class RepositorioHistorico(Protocol):
    async def listar(
        self, usuario_id: uuid.UUID, janela: timedelta, limite: int
    ) -> list[AnaliseDoHistorico]: ...

    async def apagar(self, usuario_id: uuid.UUID, analise_id: uuid.UUID) -> bool: ...

    async def apagar_todas(self, usuario_id: uuid.UUID) -> int: ...

    async def desvincular_vencidas(self, janela: timedelta) -> int: ...


class RepositorioHistoricoPostgres:
    def __init__(self, fabrica_de_sessoes: async_sessionmaker[AsyncSession]) -> None:
        self._fabrica_de_sessoes = fabrica_de_sessoes

    async def listar(
        self, usuario_id: uuid.UUID, janela: timedelta, limite: int
    ) -> list[AnaliseDoHistorico]:
        """Só as da conta e só dentro da janela — rode a desvinculação ou não."""
        async with self._fabrica_de_sessoes() as sessao:
            analises = await sessao.scalars(
                select(Analise)
                .where(
                    Analise.usuario_id == usuario_id,
                    Analise.created_at > func.now() - janela,
                )
                .order_by(Analise.created_at.desc())
                .limit(limite)
                .options(selectinload(Analise.indicadores))
            )
            return [
                AnaliseDoHistorico(
                    id=analise.id,
                    criada_em=analise.created_at,
                    # O CHECK do banco garante o vocabulário; o cast só o diz ao mypy.
                    nivel_risco=cast(NivelRisco, analise.nivel_risco),
                    score=analise.score_risco,
                    # A tabela não guarda ordem; peso e categoria dão uma ordem estável à tela.
                    fatores=tuple(
                        FatorDoHistorico(
                            categoria=indicador.categoria,
                            descricao=indicador.descricao,
                            peso=indicador.peso,
                        )
                        for indicador in sorted(
                            analise.indicadores, key=lambda i: (-i.peso, i.categoria)
                        )
                    ),
                )
                for analise in analises
            ]

    async def apagar(self, usuario_id: uuid.UUID, analise_id: uuid.UUID) -> bool:
        """DELETE de verdade. Os indicadores vão pelo ON DELETE CASCADE da 0001.

        O dono está no WHERE: a análise de outra pessoa simplesmente não casa.
        """
        async with self._fabrica_de_sessoes() as sessao, sessao.begin():
            apagada = await sessao.scalar(
                delete(Analise)
                .where(Analise.id == analise_id, Analise.usuario_id == usuario_id)
                .returning(Analise.id)
            )
        return apagada is not None

    async def apagar_todas(self, usuario_id: uuid.UUID) -> int:
        async with self._fabrica_de_sessoes() as sessao, sessao.begin():
            apagadas = await sessao.scalars(
                delete(Analise).where(Analise.usuario_id == usuario_id).returning(Analise.id)
            )
            return len(apagadas.all())

    async def desvincular_vencidas(self, janela: timedelta) -> int:
        """Depois da janela, a análise perde o dono e vira idêntica a uma anônima (ADR-0006)."""
        async with self._fabrica_de_sessoes() as sessao, sessao.begin():
            desvinculadas = await sessao.scalars(
                update(Analise)
                .where(
                    Analise.usuario_id.is_not(None),
                    Analise.created_at <= func.now() - janela,
                )
                .values(usuario_id=None)
                .returning(Analise.id)
            )
            return len(desvinculadas.all())
