"""Conta e sessão opaca: usuarios e sessoes.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-01 02:33:04.631725

Gerada por autogenerate e revisada à mão (ADR-0012, ADR-0013). O que a revisão conferiu:

- Nomes de PK, FK, UNIQUE e índice vêm da naming_convention da Base (`op.f` usa o nome pronto).
  O `uq_usuarios_email` é citado pelo repositório para traduzir a violação em 409.
- `usuarios.email` tem UNIQUE simples, sem `lower()`: o service grava o e-mail já normalizado
  (strip + minúsculas), e é o UNIQUE que decide a corrida entre dois cadastros.
- `sessoes.token_hash` é CHAR(64) com UNIQUE: o SHA-256 em hex tem sempre 64 caracteres, e o
  token em si nunca é gravado — um vazamento do banco não entrega sessão válida.
- `sessoes.usuario_id` tem ON DELETE CASCADE e índice (o Postgres não indexa FK sozinho): apagar
  a conta apaga as sessões, sem varrer a tabela.
- `sessoes.expira_em` indexada: a limpeza das vencidas filtra por ela.
- Fica de fora, de propósito: `plano` da §5.5 (errata, item 11) e qualquer mudança em `analises`
  — vínculo de análise a usuário é fatia posterior.
- Só cria tabela: é aditiva, como toda migração que roda no build do Render (ADR-0011).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("nome_exibicao", sa.String(length=60), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("senha_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usuarios")),
        sa.UniqueConstraint("email", name=op.f("uq_usuarios_email")),
    )
    op.create_table(
        "sessoes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.CHAR(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_sessoes_usuario_id_usuarios"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessoes")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sessoes_token_hash")),
    )
    op.create_index(op.f("ix_sessoes_usuario_id"), "sessoes", ["usuario_id"], unique=False)
    op.create_index(op.f("ix_sessoes_expira_em"), "sessoes", ["expira_em"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_sessoes_expira_em"), table_name="sessoes")
    op.drop_index(op.f("ix_sessoes_usuario_id"), table_name="sessoes")
    op.drop_table("sessoes")
    op.drop_table("usuarios")
