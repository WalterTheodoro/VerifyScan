"""Análise com IA: o nível do motor, o da IA, o modelo e a explicação.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-27 10:00:00.000000

Escrita à mão (ADR-0012, ADR-0020): o autogenerate não compara CHECK constraint, e os CHECKs são
metade desta migração. O que a revisão conferiu:

- É aditiva, como toda migração que roda no build do Render (ADR-0011). As quatro colunas entram
  nullable e sem default, então o código anterior, que ainda atende durante o deploy, continua
  gravando: ele não conhece as colunas e as deixa NULL.
- `nivel_motor` é preenchida nas linhas que já existem: antes da IA, o nível final era o do
  motor. O código novo sempre a preenche; uma linha com ela NULL é do código anterior.
- `nivel_motor`, `nivel_ia` e `ia_modelo` não carregam conteúdo: ficam em toda análise, anônima
  ou não, e sobrevivem à desvinculação dos 7 dias. É o que permite medir quantas vezes a IA
  subiu o nível.
- `explicacao_ia` (JSONB) é texto livre escrito pela IA a partir da mensagem e pode repetir
  trechos dela. Segue a regra do `texto_input` (0004): só com dono, e a desvinculação a zera no
  mesmo UPDATE — que este CHECK obrigaria de todo jeito.
- `ck_analises_nivel_e_o_maior`: o nível final é o maior entre o do motor e o da IA. A IA pode
  subir, nunca baixar; o banco também garante. `array_position` dá a ordem BAIXO < MEDIO < ALTO.
- Os nomes seguem a naming_convention da Base (`ck_<tabela>_<nome>`).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NIVEIS = "('BAIXO', 'MEDIO', 'ALTO')"
ORDEM = "ARRAY['BAIXO', 'MEDIO', 'ALTO']"


def upgrade() -> None:
    op.add_column("analises", sa.Column("nivel_motor", sa.String(length=10), nullable=True))
    op.add_column("analises", sa.Column("nivel_ia", sa.String(length=10), nullable=True))
    op.add_column("analises", sa.Column("ia_modelo", sa.String(length=100), nullable=True))
    op.add_column(
        "analises",
        sa.Column("explicacao_ia", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.execute("UPDATE analises SET nivel_motor = nivel_risco")

    op.create_check_constraint(
        op.f("ck_analises_nivel_motor"), "analises", f"nivel_motor IN {NIVEIS}"
    )
    op.create_check_constraint(op.f("ck_analises_nivel_ia"), "analises", f"nivel_ia IN {NIVEIS}")
    op.create_check_constraint(
        op.f("ck_analises_ia_com_modelo"), "analises", "(nivel_ia IS NULL) = (ia_modelo IS NULL)"
    )
    op.create_check_constraint(
        op.f("ck_analises_nivel_e_o_maior"),
        "analises",
        "nivel_motor IS NULL OR nivel_risco = CASE "
        f"WHEN nivel_ia IS NOT NULL AND array_position({ORDEM}, nivel_ia::text) > "
        f"array_position({ORDEM}, nivel_motor::text) "
        "THEN nivel_ia ELSE nivel_motor END",
    )
    op.create_check_constraint(
        op.f("ck_analises_explicacao_so_com_dono"),
        "analises",
        "explicacao_ia IS NULL OR usuario_id IS NOT NULL",
    )
    op.create_check_constraint(
        op.f("ck_analises_explicacao_com_ia"),
        "analises",
        "explicacao_ia IS NULL OR nivel_ia IS NOT NULL",
    )
    op.create_check_constraint(
        op.f("ck_analises_explicacao_ate_4000"),
        "analises",
        "char_length(explicacao_ia::text) <= 4000",
    )


def downgrade() -> None:
    for nome in (
        "ck_analises_explicacao_ate_4000",
        "ck_analises_explicacao_com_ia",
        "ck_analises_explicacao_so_com_dono",
        "ck_analises_nivel_e_o_maior",
        "ck_analises_ia_com_modelo",
        "ck_analises_nivel_ia",
        "ck_analises_nivel_motor",
    ):
        op.drop_constraint(op.f(nome), "analises", type_="check")
    op.drop_column("analises", "explicacao_ia")
    op.drop_column("analises", "ia_modelo")
    op.drop_column("analises", "nivel_ia")
    op.drop_column("analises", "nivel_motor")
