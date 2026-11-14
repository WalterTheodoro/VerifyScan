"""Uso diário (cota da IA e cadastros por IP) e gasto agregado da IA.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-14 12:00:00.000000

Escrita à mão (ADR-0012, ADR-0024): o autogenerate não compara CHECK constraint. O que a revisão
conferiu:

- É aditiva, como toda migração que roda no build do Render (ADR-0011): duas tabelas novas,
  nenhuma coluna mexida. O código anterior não as conhece e segue funcionando durante o deploy.
- `uso_diario`: chave primária `(finalidade, chave, dia)`. É ela que faz o UPSERT da cota ser
  atômico — `INSERT … ON CONFLICT … DO UPDATE … WHERE unidades + n <= limite RETURNING`: dois
  pedidos simultâneos na mesma chave disputam a trava da mesma linha, e o segundo já vê a soma
  do primeiro. Índice em `dia`, que não é a primeira coluna da chave, para a faxina.
- A `chave` é `conta:<uuid>` ou `ip:<HMAC-SHA256 do IP>` — nunca o IP. Não há id de análise nem
  hora por pedido: a chave não liga análises anônimas entre si (ADR-0006).
- `ck_uso_diario_unidades_positivas`: linha só existe com uso; o UPSERT nunca grava zero.
- `gasto_diario_ia`: uma linha por dia, de todo mundo, sem pessoa. `custo_usd` em NUMERIC(12,6),
  dinheiro sem o arredondamento do float. `chamadas_com_timeout` mede o gasto que fica fora da
  conta: chamada cortada pelo nosso teto não devolve usage. `teto_avisado` faz o WARNING de teto
  sair uma vez por dia mesmo com o processo reiniciando.
- Os nomes seguem a naming_convention da Base (`ck_<tabela>_<nome>`, `pk_<tabela>`,
  `ix_<tabela>_<coluna>`).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "uso_diario",
        sa.Column("finalidade", sa.String(length=20), nullable=False),
        sa.Column("chave", sa.String(length=80), nullable=False),
        sa.Column("dia", sa.Date(), nullable=False),
        sa.Column("unidades", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "finalidade IN ('ia', 'cadastro')", name=op.f("ck_uso_diario_finalidade")
        ),
        sa.CheckConstraint("unidades > 0", name=op.f("ck_uso_diario_unidades_positivas")),
        sa.PrimaryKeyConstraint("finalidade", "chave", "dia", name=op.f("pk_uso_diario")),
    )
    op.create_index(op.f("ix_uso_diario_dia"), "uso_diario", ["dia"], unique=False)

    op.create_table(
        "gasto_diario_ia",
        sa.Column("dia", sa.Date(), nullable=False),
        sa.Column("tokens_entrada", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("tokens_saida", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("custo_usd", sa.Numeric(precision=12, scale=6), server_default="0", nullable=False),
        sa.Column("chamadas", sa.Integer(), server_default="0", nullable=False),
        sa.Column("chamadas_com_timeout", sa.Integer(), server_default="0", nullable=False),
        sa.Column("teto_avisado", sa.Boolean(), server_default="false", nullable=False),
        sa.CheckConstraint("tokens_entrada >= 0", name=op.f("ck_gasto_diario_ia_tokens_entrada")),
        sa.CheckConstraint("tokens_saida >= 0", name=op.f("ck_gasto_diario_ia_tokens_saida")),
        sa.CheckConstraint("custo_usd >= 0", name=op.f("ck_gasto_diario_ia_custo_usd")),
        sa.CheckConstraint("chamadas >= 0", name=op.f("ck_gasto_diario_ia_chamadas")),
        sa.CheckConstraint(
            "chamadas_com_timeout >= 0", name=op.f("ck_gasto_diario_ia_chamadas_com_timeout")
        ),
        sa.PrimaryKeyConstraint("dia", name=op.f("pk_gasto_diario_ia")),
    )


def downgrade() -> None:
    op.drop_table("gasto_diario_ia")
    op.drop_index(op.f("ix_uso_diario_dia"), table_name="uso_diario")
    op.drop_table("uso_diario")
