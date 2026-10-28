"""Tabelas da análise: `analises` e `indicadores_risco` (§5.5 do RFC, ADR-0012).

`usuario_id` liga a análise feita logado à conta, por `HISTORICO_DIAS` (ADR-0015). `texto_input`
guarda a mensagem só enquanto esse vínculo existe (ADR-0018). Anônima, ou depois da janela, as
duas colunas ficam `NULL` — e então a análise é idêntica a uma anônima do ADR-0006.

A análise com IA (ADR-0020) acrescenta `nivel_motor`, `nivel_ia` e `ia_modelo`, que não carregam
conteúdo e ficam em toda análise, e `explicacao_ia`, que segue a regra do `texto_input`.

O print da conversa (ADR-0023, migração 0006) não tem coluna para a imagem — ela nunca é guardada.
Para quem tem conta, a transcrição vai em `texto_input`, e o contexto da tela em `contexto_print`,
com a regra da `explicacao_ia`.

O que NÃO está aqui, de propósito:
- `urls_analisadas`: a forma canônica preserva a query string (ADR-0009), que pode carregar
  e-mail ou token da vítima;
- `resultado` (§5.5): o RFC não define o conteúdo; o único uso ligado a persistência é a Tela 5,
  onde "resultado" é o nível de risco — já coberto por `nivel_risco`.
"""

import uuid
from datetime import datetime
from typing import Any, get_args

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.schemas.analise import NivelRisco, TipoFator, TipoInput


def _check_valores(coluna: str, valores: tuple[str, ...]) -> str:
    """`coluna IN ('A', 'B')` a partir do Literal do schema — um vocabulário só (errata item 8).

    VARCHAR + CHECK em vez de ENUM nativo: ENUM exige migração manual a cada valor novo.
    """
    return f"{coluna} IN ({', '.join(repr(valor) for valor in valores)})"


# A IA pode subir o nível, nunca baixar: o banco também garante (ADR-0020). `nivel_motor` NULL é
# a linha gravada pelo código anterior durante o deploy (a coluna entrou nullable na 0005).
NIVEL_E_O_MAIOR = (
    "nivel_motor IS NULL OR nivel_risco = CASE "
    "WHEN nivel_ia IS NOT NULL AND "
    "array_position(ARRAY['BAIXO', 'MEDIO', 'ALTO'], nivel_ia::text) > "
    "array_position(ARRAY['BAIXO', 'MEDIO', 'ALTO'], nivel_motor::text) "
    "THEN nivel_ia ELSE nivel_motor END"
)


class Analise(Base):
    __tablename__ = "analises"
    __table_args__ = (
        CheckConstraint(_check_valores("nivel_risco", get_args(NivelRisco)), name="nivel_risco"),
        CheckConstraint(_check_valores("tipo_input", get_args(TipoInput)), name="tipo_input"),
        # Análise anônima nunca tem texto (ADR-0006): quem garante é o banco (ADR-0018).
        CheckConstraint("texto_input IS NULL OR usuario_id IS NOT NULL", name="texto_so_com_dono"),
        # O teto de TEXTO_MAX_CARACTERES; o Settings recusa valor maior (migração 0004).
        CheckConstraint("char_length(texto_input) <= 5000", name="texto_ate_5000"),
        # Análise com IA (migração 0005, ADR-0020).
        CheckConstraint(_check_valores("nivel_motor", get_args(NivelRisco)), name="nivel_motor"),
        CheckConstraint(_check_valores("nivel_ia", get_args(NivelRisco)), name="nivel_ia"),
        CheckConstraint("(nivel_ia IS NULL) = (ia_modelo IS NULL)", name="ia_com_modelo"),
        CheckConstraint(NIVEL_E_O_MAIOR, name="nivel_e_o_maior"),
        CheckConstraint(
            "explicacao_ia IS NULL OR usuario_id IS NOT NULL", name="explicacao_so_com_dono"
        ),
        CheckConstraint("explicacao_ia IS NULL OR nivel_ia IS NOT NULL", name="explicacao_com_ia"),
        CheckConstraint("char_length(explicacao_ia::text) <= 4000", name="explicacao_ate_4000"),
        # Print da conversa (migração 0006, ADR-0023).
        CheckConstraint(
            "contexto_print IS NULL OR usuario_id IS NOT NULL", name="contexto_print_so_com_dono"
        ),
        CheckConstraint(
            "contexto_print IS NULL OR tipo_input = 'imagem'", name="contexto_print_so_de_imagem"
        ),
        CheckConstraint("char_length(contexto_print::text) <= 500", name="contexto_print_ate_500"),
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
    # A mensagem como chegou, só para quem está logado e só pela janela do histórico: a
    # desvinculação zera esta coluna junto com `usuario_id` (ADR-0018). Num print, é a
    # transcrição, com quem mandou cada mensagem (ADR-0023).
    texto_input: Mapped[str | None] = mapped_column(Text)
    # O nível do motor sozinho e o sugerido pela IA; `nivel_risco` é o maior dos dois (ADR-0020).
    nivel_motor: Mapped[str | None] = mapped_column(String(10))
    nivel_ia: Mapped[str | None] = mapped_column(String(10))
    ia_modelo: Mapped[str | None] = mapped_column(String(100))
    # Tipo, sinais e passos que a IA escreveu, já limpos. Podem repetir trechos da mensagem: só
    # com dono, e a desvinculação zera junto com o texto (ADR-0020). `none_as_null`: sem ele, o
    # `None` do Python vira o JSON `null`, que não é o NULL do SQL — e os CHECKs recusariam.
    explicacao_ia: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    # O conjunto fechado que a leitura do print preenche (ADR-0023). Revela se a pessoa tem alguém
    # salvo nos contatos: só com dono, e a desvinculação zera junto com o texto.
    contexto_print: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))

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
