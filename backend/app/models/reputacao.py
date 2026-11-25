"""Reputação de links: `reputacao_cache` e `reputacao_uso` (ADR-0028, migração 0008).

`reputacao_cache` guarda o que uma base externa respondeu sobre um domínio, até vencer. A chave é
o SHA-256 do host (Safe Browsing) ou do domínio registrável (VirusTotal): o domínio em claro não
é gravado. Não há pessoa, análise nem hora do pedido: a linha não liga ninguém a nada.

O RFC (§5.4.4) põe esse cache no Redis. Ficou no Postgres porque o Redis está desligado em
produção; o desvio está na errata.

`reputacao_uso` conta as consultas ao VirusTotal por janela (minuto e dia, em UTC), de todo
mundo: é o que mantém o sistema dentro do limite da API pública.
"""

from datetime import datetime
from typing import get_args

from sqlalchemy import CheckConstraint, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.reputation.tipos import Veredito
from app.schemas.analise import FonteReputacao

JANELAS = ("minuto", "dia")

_FONTES = ", ".join(repr(valor) for valor in get_args(FonteReputacao))
_VEREDITOS = ", ".join(repr(valor) for valor in get_args(Veredito))
_JANELAS = ", ".join(repr(valor) for valor in JANELAS)


class ReputacaoCache(Base):
    __tablename__ = "reputacao_cache"
    __table_args__ = (
        CheckConstraint(f"fonte IN ({_FONTES})", name="fonte"),
        CheckConstraint(f"veredito IN ({_VEREDITOS})", name="veredito"),
    )

    fonte: Mapped[str] = mapped_column(String(20), primary_key=True)
    # SHA-256 em hexadecimal.
    chave: Mapped[str] = mapped_column(String(64), primary_key=True)
    veredito: Mapped[str] = mapped_column(String(12))
    # Indexado: a leitura filtra por ele e a limpeza apaga por ele.
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ReputacaoUso(Base):
    __tablename__ = "reputacao_uso"
    __table_args__ = (
        CheckConstraint(f"fonte IN ({_FONTES})", name="fonte"),
        CheckConstraint(f"janela IN ({_JANELAS})", name="janela"),
        CheckConstraint("consultas > 0", name="consultas_positivas"),
    )

    fonte: Mapped[str] = mapped_column(String(20), primary_key=True)
    janela: Mapped[str] = mapped_column(String(6), primary_key=True)
    # O começo do minuto ou do dia, em UTC.
    inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    consultas: Mapped[int] = mapped_column(Integer)
