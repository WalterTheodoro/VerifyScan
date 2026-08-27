"""Base declarativa do SQLAlchemy.

Sem nenhuma tabela ainda: `Usuario`, `Analise` e `IndicadorRisco` entram na Fase 8. A base
existe desde já porque o Alembic precisa de um `target_metadata` para comparar.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
