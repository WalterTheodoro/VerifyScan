"""Texto da análise feita com conta: analises.texto_input.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-26 10:00:00.000000

Escrita à mão (ADR-0012, ADR-0018): o autogenerate não compara CHECK constraint, e os dois
CHECKs são o motivo desta migração. O que a revisão conferiu:

- `texto_input` (nome da §5.5 do RFC) é TEXT, nullable e sem default. Coluna nullable sem default
  não reescreve a tabela no Postgres 16: as análises que já existem ficam sem texto, que é o que
  elas são.
- `ck_analises_texto_so_com_dono`: quem garante que análise anônima nunca tem texto é o banco, e
  não só o código (ADR-0006 continua valendo). Como a desvinculação dos 7 dias zera `usuario_id`
  e `texto_input` no mesmo UPDATE, a regra vale também depois da janela.
- `ck_analises_texto_ate_5000`: o teto de `TEXTO_MAX_CARACTERES`, escrito por extenso. O
  `Settings` recusa valor maior (`le=5000`): subir o limite exige migração nova junto.
  `char_length` conta caracteres, como o `len` do Python que valida a entrada.
- Os nomes seguem a naming_convention da Base (`ck_<tabela>_<nome>`).
- É aditiva, como toda migração que roda no build do Render (ADR-0011).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("analises", sa.Column("texto_input", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_analises_texto_so_com_dono"),
        "analises",
        "texto_input IS NULL OR usuario_id IS NOT NULL",
    )
    op.create_check_constraint(
        op.f("ck_analises_texto_ate_5000"),
        "analises",
        "char_length(texto_input) <= 5000",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_analises_texto_ate_5000"), "analises", type_="check")
    op.drop_constraint(op.f("ck_analises_texto_so_com_dono"), "analises", type_="check")
    op.drop_column("analises", "texto_input")
