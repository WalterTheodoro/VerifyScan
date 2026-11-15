"""Uso diário e gasto da IA: `uso_diario` e `gasto_diario_ia` (fatia 10, ADR-0024).

`uso_diario` conta, por chave e por dia de São Paulo, as unidades gastas: análises com IA
(`finalidade='ia'`, texto 1 e print 3) e contas criadas (`finalidade='cadastro'`). A chave é
`conta:<id>` para quem tem conta e `ip:<hmac>` para quem não tem — o HMAC do IP com um segredo do
servidor, nunca o IP. É dado pseudonimizado: ainda pessoal, guardado por no máximo 2 dias.

O que NÃO está aqui, de propósito: o id da análise e a hora de cada pedido. Com eles, a chave
ligaria entre si as análises anônimas de uma mesma pessoa, que o ADR-0006 mantém soltas.

`gasto_diario_ia` é o total do dia, de todo mundo, sem pessoa: tokens que a API devolveu, o custo
calculado com os preços do `Settings`, as chamadas e as que terminaram em timeout — essas não
devolvem usage, e a contagem mede o que ficou fora do custo.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal, get_args

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Um vocabulário só para o tipo e o CHECK, como em `analise.py`.
Finalidade = Literal["ia", "cadastro"]
_FINALIDADES = ", ".join(repr(valor) for valor in get_args(Finalidade))


def chave_da_conta(usuario_id: uuid.UUID) -> str:
    """A chave de quem tem conta. Aqui, junto da tabela: a exclusão da conta apaga por ela."""
    return f"conta:{usuario_id}"


def chave_do_ip(hmac_do_ip: str) -> str:
    """A chave de quem não tem conta: o HMAC do IP, nunca o IP (`app/core/ip.py`)."""
    return f"ip:{hmac_do_ip}"


class UsoDiario(Base):
    __tablename__ = "uso_diario"
    __table_args__ = (
        CheckConstraint(f"finalidade IN ({_FINALIDADES})", name="finalidade"),
        CheckConstraint("unidades > 0", name="unidades_positivas"),
    )

    finalidade: Mapped[str] = mapped_column(String(20), primary_key=True)
    # `conta:` + uuid (42) ou `ip:` + HMAC-SHA256 em hex (67).
    chave: Mapped[str] = mapped_column(String(80), primary_key=True)
    # Indexado: a faxina apaga por dia, e o dia não é a primeira coluna da chave primária.
    dia: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
    unidades: Mapped[int] = mapped_column(Integer)


class GastoDiarioIA(Base):
    __tablename__ = "gasto_diario_ia"
    __table_args__ = (
        CheckConstraint("tokens_entrada >= 0", name="tokens_entrada"),
        CheckConstraint("tokens_saida >= 0", name="tokens_saida"),
        CheckConstraint("custo_usd >= 0", name="custo_usd"),
        CheckConstraint("chamadas >= 0", name="chamadas"),
        CheckConstraint("chamadas_com_timeout >= 0", name="chamadas_com_timeout"),
    )

    dia: Mapped[date] = mapped_column(Date, primary_key=True)
    tokens_entrada: Mapped[int] = mapped_column(BigInteger, server_default="0")
    tokens_saida: Mapped[int] = mapped_column(BigInteger, server_default="0")
    # Seis casas: uma chamada custa centésimos de centavo de dólar.
    custo_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), server_default="0")
    # Chamadas que voltaram com usage, entrando no custo.
    chamadas: Mapped[int] = mapped_column(Integer, server_default="0")
    # Cortadas pelo nosso teto de tempo: sem usage, fora do custo, mas contadas.
    chamadas_com_timeout: Mapped[int] = mapped_column(Integer, server_default="0")
    # O WARNING de "teto atingido" sai uma vez por dia, mesmo com o processo reiniciando.
    teto_avisado: Mapped[bool] = mapped_column(Boolean, server_default="false")
