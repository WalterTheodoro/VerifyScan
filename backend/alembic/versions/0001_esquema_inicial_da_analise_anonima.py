"""Esquema inicial da análise anônima: analises e indicadores_risco.

Revision ID: 0001
Revises:
Create Date: 2026-10-01 01:19:28.286456

Gerada por autogenerate e revisada à mão (ADR-0012). O que a revisão conferiu:

- Nomes de PK, FK, índice e CHECK vêm da naming_convention da Base (`op.f` usa o nome pronto).
- Os valores dos CHECKs estão escritos aqui por extenso, e não importados de `app.schemas`: uma
  migração é uma foto do esquema naquele momento. Se o Literal ganhar um valor, quem amplia o
  CHECK é uma migração nova — e o `alembic check` NÃO percebe a divergência (o autogenerate não
  compara CHECK). Por isso existe `tests/integracao/test_checks.py`.
- Fica de fora, de propósito: texto da mensagem e usuario_id (ADR-0006; dependem do ADR de
  privacidade do autenticado), urls_analisadas (ADR-0009 preserva a query) e `resultado` (§5.5,
  sem conteúdo definido; o nível de risco já está em nivel_risco).
- Só cria tabela: é aditiva, como toda migração que roda no build do Render (ADR-0011).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analises",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("score_risco", sa.Integer(), nullable=False),
        sa.Column("nivel_risco", sa.String(length=10), nullable=False),
        sa.Column("tipo_input", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "nivel_risco IN ('BAIXO', 'MEDIO', 'ALTO')",
            name=op.f("ck_analises_nivel_risco"),
        ),
        sa.CheckConstraint("tipo_input IN ('texto')", name=op.f("ck_analises_tipo_input")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analises")),
    )
    op.create_table(
        "indicadores_risco",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("analise_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        # Sem CHECK: as categorias crescem nas Fases 3 e 4; quem valida é o Literal do Pydantic.
        sa.Column("categoria", sa.String(length=50), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("peso", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "tipo IN ('texto', 'dominio', 'reputacao')",
            name=op.f("ck_indicadores_risco_tipo"),
        ),
        sa.CheckConstraint("peso > 0", name=op.f("ck_indicadores_risco_peso_positivo")),
        sa.ForeignKeyConstraint(
            ["analise_id"],
            ["analises.id"],
            name=op.f("fk_indicadores_risco_analise_id_analises"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_indicadores_risco")),
    )
    # O Postgres não indexa FK sozinho. Sem este índice, todo DELETE em analises (o cascade, e
    # a exclusão de conta da Fase 8) varreria indicadores_risco inteira.
    op.create_index(
        op.f("ix_indicadores_risco_analise_id"),
        "indicadores_risco",
        ["analise_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_indicadores_risco_analise_id"), table_name="indicadores_risco")
    op.drop_table("indicadores_risco")
    op.drop_table("analises")
