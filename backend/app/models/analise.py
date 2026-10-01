"""Tabelas da análise: `analises` e `indicadores_risco` (§5.5 do RFC, ADR-0012).

`usuario_id` liga a análise feita logado à conta, por `HISTORICO_DIAS` (ADR-0015). Anônima, ou
depois da janela, fica `NULL` — e então é idêntica a uma análise anônima do ADR-0006.

O que NÃO está aqui, de propósito:
- texto da mensagem, nem trecho dele, para nenhum usuário: o histórico se reconhece pela data,
  pelo nível e pelos fatores (ADR-0006, ADR-0015);
- `urls_analisadas`: a forma canônica preserva a query string (ADR-0009), que pode carregar
  e-mail ou token da vítima;
- `resultado` (§5.5): o RFC não define o conteúdo; o único uso ligado a persistência é a Tela 5,
  onde "resultado" é o nível de risco — já coberto por `nivel_risco`.
"""

import uuid
from datetime import datetime
from typing import get_args

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.schemas.analise import NivelRisco, TipoFator, TipoInput


def _check_valores(coluna: str, valores: tuple[str, ...]) -> str:
    """`coluna IN ('A', 'B')` a partir do Literal do schema — um vocabulário só (errata item 8).

    VARCHAR + CHECK em vez de ENUM nativo: ENUM exige migração manual a cada valor novo.
    """
    return f"{coluna} IN ({', '.join(repr(valor) for valor in valores)})"


class Analise(Base):
    __tablename__ = "analises"
    __table_args__ = (
        CheckConstraint(_check_valores("nivel_risco", get_args(NivelRisco)), name="nivel_risco"),
        CheckConstraint(_check_valores("tipo_input", get_args(TipoInput)), name="tipo_input"),
        # A listagem filtra pelo dono e pela janela e ordena por data: um índice serve às duas
        # coisas, e com `usuario_id` na frente também cobre a FK no CASCADE (ADR-0015).
        Index("ix_analises_usuario_id_created_at", "usuario_id", "created_at"),
    )

    # UUID gerado em Python: o id vai aparecer em /api/historico/{id}, e inteiro sequencial é
    # enumerável.
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    score_risco: Mapped[int]
    nivel_risco: Mapped[str] = mapped_column(String(10))
    tipo_input: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # ON DELETE CASCADE: apagar a conta apaga as análises ainda ligadas a ela (ADR-0015).
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE")
    )

    # lazy="raise": acessar sem `selectinload` explícito levanta erro em vez de disparar I/O
    # escondido. É a regra 2 do ADR-0001 garantida pelo ORM, não pela memória.
    # passive_deletes: quem apaga os indicadores é o ON DELETE CASCADE do banco.
    indicadores: Mapped[list["IndicadorRisco"]] = relationship(
        back_populates="analise",
        lazy="raise",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class IndicadorRisco(Base):
    """Um fator que somou pontos (invariante 6): o registro de auditoria e de recalibração."""

    __tablename__ = "indicadores_risco"
    __table_args__ = (
        CheckConstraint(_check_valores("tipo", get_args(TipoFator)), name="tipo"),
        CheckConstraint("peso > 0", name="peso_positivo"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    analise_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analises.id", ondelete="CASCADE"), index=True
    )
    tipo: Mapped[str] = mapped_column(String(20))
    # Sem CHECK: cresce na Fase 3 (domínio) e na Fase 4 (reputação). Quem valida é o Literal
    # `CategoriaFator` do Pydantic, antes de chegar aqui.
    categoria: Mapped[str] = mapped_column(String(50))
    descricao: Mapped[str] = mapped_column(Text)
    peso: Mapped[int]

    analise: Mapped[Analise] = relationship(back_populates="indicadores", lazy="raise")
