"""Base declarativa do SQLAlchemy, com as convenções do esquema (ADR-0012).

A `naming_convention` é a da documentação do SQLAlchemy. Sem ela, o Postgres inventa o nome de
índice, CHECK e FK, e o nome inventado é o que uma migração futura precisaria citar para alterar
ou remover a constraint. Decidida antes da primeira migração: trocar depois é migração de
renomeação sobre dado já gravado.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

CONVENCAO_DE_NOMES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=CONVENCAO_DE_NOMES)
