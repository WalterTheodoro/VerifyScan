"""Reputação de links: cache das respostas e contador de consultas.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-25 12:00:00.000000

Escrita à mão (ADR-0012, ADR-0028): o autogenerate não compara CHECK constraint. O que a revisão
conferiu:

- É aditiva, como toda migração que roda no build do Render (ADR-0011): duas tabelas novas,
  nenhuma coluna mexida. O código anterior não as conhece e segue funcionando durante o deploy.
- `reputacao_cache`: chave primária `(fonte, chave)`. A `chave` é o SHA-256 do host ou do domínio
  registrável, nunca o domínio em claro. Sem pessoa, sem análise, sem hora do pedido. Índice em
  `expira_em`, que a leitura filtra e a limpeza apaga.
- `reputacao_uso`: chave primária `(fonte, janela, inicio)`. É ela que faz a reserva ser atômica
  — `INSERT … ON CONFLICT … DO UPDATE … WHERE consultas + n <= limite RETURNING`, como no
  `uso_diario` da 0007.
- `ck_reputacao_uso_consultas_positivas`: linha só existe com uso.
- Os nomes seguem a naming_convention da Base (`ck_<tabela>_<nome>`, `pk_<tabela>`,
  `ix_<tabela>_<coluna>`).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FONTES = "fonte IN ('safe_browsing', 'virustotal')"


def upgrade() -> None:
    op.create_table(
        "reputacao_cache",
        sa.Column("fonte", sa.String(length=20), nullable=False),
        sa.Column("chave", sa.String(length=64), nullable=False),
        sa.Column("veredito", sa.String(length=12), nullable=False),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(_FONTES, name=op.f("ck_reputacao_cache_fonte")),
        sa.CheckConstraint(
            "veredito IN ('limpo', 'suspeito', 'malicioso')",
            name=op.f("ck_reputacao_cache_veredito"),
        ),
        sa.PrimaryKeyConstraint("fonte", "chave", name=op.f("pk_reputacao_cache")),
    )
    op.create_index(
        op.f("ix_reputacao_cache_expira_em"), "reputacao_cache", ["expira_em"], unique=False
    )

    op.create_table(
        "reputacao_uso",
        sa.Column("fonte", sa.String(length=20), nullable=False),
        sa.Column("janela", sa.String(length=6), nullable=False),
        sa.Column("inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consultas", sa.Integer(), nullable=False),
        sa.CheckConstraint(_FONTES, name=op.f("ck_reputacao_uso_fonte")),
        sa.CheckConstraint("janela IN ('minuto', 'dia')", name=op.f("ck_reputacao_uso_janela")),
        sa.CheckConstraint("consultas > 0", name=op.f("ck_reputacao_uso_consultas_positivas")),
        sa.PrimaryKeyConstraint("fonte", "janela", "inicio", name=op.f("pk_reputacao_uso")),
    )


def downgrade() -> None:
    op.drop_table("reputacao_uso")
    op.drop_index(op.f("ix_reputacao_cache_expira_em"), table_name="reputacao_cache")
    op.drop_table("reputacao_cache")
