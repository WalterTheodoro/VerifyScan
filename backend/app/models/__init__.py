"""Modelos SQLAlchemy. Importar o pacote registra todas as tabelas no metadata da `Base`.

`Usuario` entra numa fatia posterior da Fase 8, com o ADR de privacidade do autenticado.
"""

from app.models.analise import Analise, IndicadorRisco

__all__ = ["Analise", "IndicadorRisco"]
