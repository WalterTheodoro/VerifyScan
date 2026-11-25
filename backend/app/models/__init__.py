"""Modelos SQLAlchemy. Importar o pacote registra todas as tabelas no metadata da `Base`.

Modelo novo precisa entrar aqui: o `alembic check` só enxerga o que foi importado.
"""

from app.models.analise import Analise, IndicadorRisco
from app.models.reputacao import ReputacaoCache, ReputacaoUso
from app.models.uso import GastoDiarioIA, UsoDiario
from app.models.usuario import SessaoUsuario, Usuario

__all__ = [
    "Analise",
    "GastoDiarioIA",
    "IndicadorRisco",
    "ReputacaoCache",
    "ReputacaoUso",
    "SessaoUsuario",
    "UsoDiario",
    "Usuario",
]
