"""Vínculo da análise à conta: analises.usuario_id.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-01 15:40:19.664597

Gerada por autogenerate e revisada à mão (ADR-0012, ADR-0015). O que a revisão conferiu:

- `usuario_id` é nullable e sem default: anônima, ou depois da janela de `HISTORICO_DIAS`, fica
  NULL. Coluna nullable sem default não reescreve a tabela no Postgres 16 — as análises que já
  existem continuam anônimas, que é o que elas são.
- FK `fk_analises_usuario_id_usuarios` (naming_convention da Base) com ON DELETE CASCADE: apagar
  a conta apaga as análises ainda ligadas a ela, e os indicadores vão junto pelo CASCADE da 0001.
- Índice composto `(usuario_id, created_at)`: a listagem filtra pelo dono e pela janela e ordena
  por data. Não há índice simples em `usuario_id` porque o composto, com ele na frente, já serve
  à FK no CASCADE (o Postgres não indexa FK sozinho).
- O índice não é `CONCURRENTLY`: o Alembic roda a migração numa transação, e a tabela é pequena.
- Não entra coluna de texto: o histórico não guarda a mensagem nem trecho dela (ADR-0015).
- É aditiva, como toda migração que roda no build do Render (ADR-0011).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("analises", sa.Column("usuario_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_analises_usuario_id_usuarios"),
        "analises",
        "usuarios",
        ["usuario_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_analises_usuario_id_created_at",
        "analises",
        ["usuario_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_analises_usuario_id_created_at", table_name="analises")
    op.drop_constraint(op.f("fk_analises_usuario_id_usuarios"), "analises", type_="foreignkey")
    op.drop_column("analises", "usuario_id")
