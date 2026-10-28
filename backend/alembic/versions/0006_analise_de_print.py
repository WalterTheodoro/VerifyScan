"""Análise de print: tipo_input 'imagem' e o contexto do print, só com dono.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-27 21:00:00.000000

Escrita à mão (ADR-0012, ADR-0023): o autogenerate não compara CHECK constraint, e os CHECKs são
quase toda esta migração. O que a revisão conferiu:

- É aditiva, como toda migração que roda no build do Render (ADR-0011). O CHECK do `tipo_input`
  é ampliado (sai e volta com `'imagem'` a mais): o código anterior só grava `'texto'`, que segue
  válido durante o deploy. `contexto_print` entra nullable e sem default, sem reescrever a tabela.
- A IMAGEM não tem coluna, e não vai ter: nunca é guardada (invariante 2). O que se guarda de um
  print, para quem tem conta, é a transcrição em `texto_input`, com as regras da 0004 (só com
  dono, até 5000 caracteres, zerada na desvinculação). O ADR-0023 substitui a frase do ADR-0006
  que proibia guardar texto de OCR.
- `contexto_print` (JSONB) é o conjunto fechado que a leitura preenche: canal, se quem mandou está
  salvo nos contatos, aviso do aplicativo, primeira mensagem, link visível. Revela se a pessoa tem
  alguém salvo nos contatos: segue a regra da `explicacao_ia` (0005) — só com dono, e a
  desvinculação o zera no mesmo UPDATE, que este CHECK obrigaria de todo jeito.
- `ck_analises_contexto_print_so_de_imagem`: análise de texto não tem contexto de print.
- `ck_analises_contexto_print_ate_500`: os cinco campos, com os valores mais longos, somam menos de
  200 caracteres em JSON. 500 deixa folga para um campo novo sem abrir espaço para texto livre.
- Os nomes seguem a naming_convention da Base (`ck_<tabela>_<nome>`).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_analises_tipo_input"), "analises", type_="check")
    op.create_check_constraint(
        op.f("ck_analises_tipo_input"), "analises", "tipo_input IN ('texto', 'imagem')"
    )
    op.add_column(
        "analises",
        sa.Column("contexto_print", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_analises_contexto_print_so_com_dono"),
        "analises",
        "contexto_print IS NULL OR usuario_id IS NOT NULL",
    )
    op.create_check_constraint(
        op.f("ck_analises_contexto_print_so_de_imagem"),
        "analises",
        "contexto_print IS NULL OR tipo_input = 'imagem'",
    )
    op.create_check_constraint(
        op.f("ck_analises_contexto_print_ate_500"),
        "analises",
        "char_length(contexto_print::text) <= 500",
    )


def downgrade() -> None:
    """Volta ao esquema da 0005. As análises de imagem viram `texto` só para caber no CHECK
    antigo; o downgrade é ferramenta de teste (o CI desce e sobe o esquema), não caminho de
    produção."""
    for nome in (
        "ck_analises_contexto_print_ate_500",
        "ck_analises_contexto_print_so_de_imagem",
        "ck_analises_contexto_print_so_com_dono",
    ):
        op.drop_constraint(op.f(nome), "analises", type_="check")
    op.drop_column("analises", "contexto_print")
    op.drop_constraint(op.f("ck_analises_tipo_input"), "analises", type_="check")
    op.execute("UPDATE analises SET tipo_input = 'texto' WHERE tipo_input = 'imagem'")
    op.create_check_constraint(
        op.f("ck_analises_tipo_input"), "analises", "tipo_input IN ('texto')"
    )
