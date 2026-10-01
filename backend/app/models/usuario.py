"""Conta e sessão: `usuarios` e `sessoes` (ADR-0013), nas convenções do ADR-0012.

Diverge da §5.5 do RFC (errata, item 11): entra `nome_exibicao`, com a finalidade de saudação na
interface — não é "nome completo" —, e não entra `plano`.

O que NÃO está aqui: vínculo de `analises` ao usuário e histórico (fatia posterior).
"""

import uuid
from datetime import datetime

from sqlalchemy import CHAR, DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    nome_exibicao: Mapped[str] = mapped_column(String(60))
    # Gravado já normalizado (strip + minúsculas) pelo service: o UNIQUE simples basta.
    email: Mapped[str] = mapped_column(String(254), unique=True)
    senha_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # passive_deletes: quem apaga as sessões é o ON DELETE CASCADE do banco — é o que faz a
    # exclusão de conta não deixar sessão válida para trás.
    sessoes: Mapped[list["SessaoUsuario"]] = relationship(
        back_populates="usuario",
        lazy="raise",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class SessaoUsuario(Base):
    """Sessão opaca. `SessaoUsuario`, e não `Sessao`: `sessao` já é a AsyncSession no código."""

    __tablename__ = "sessoes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    # SHA-256 em hex do token do cookie — sempre 64 caracteres. O token em si nunca é gravado:
    # um vazamento do banco não entrega sessão válida.
    token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Indexada: a limpeza das vencidas e a checagem de validade filtram por ela.
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    usuario: Mapped[Usuario] = relationship(back_populates="sessoes", lazy="raise")
