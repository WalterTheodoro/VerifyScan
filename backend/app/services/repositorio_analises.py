"""Registro da análise no banco — mesmo padrão do `VerificadorSaude`: um Protocol, uma
implementação real e um falso em memória nos testes.
"""

import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Analise, IndicadorRisco
from app.schemas.analise import Fator, NivelRisco, RespostaAnalise, TipoInput


@dataclass(frozen=True)
class RegistroAnalise:
    """Tudo o que o banco recebe de uma análise anônima — e nada além disso.

    Não há campo para o texto (ADR-0006) nem para as URLs (ADR-0009 preserva a query, que pode
    carregar e-mail ou token da vítima). A regra fica no tipo: o repositório não tem por onde
    receber esses dados, do mesmo jeito que o AIFormulator não tem por onde receber a mensagem
    (invariante 1).
    """

    score: int
    nivel_risco: NivelRisco
    tipo_input: TipoInput
    fatores: tuple[Fator, ...]

    @classmethod
    def da_resposta(cls, resposta: RespostaAnalise, tipo_input: TipoInput) -> "RegistroAnalise":
        return cls(
            score=resposta.score,
            nivel_risco=resposta.nivel_risco,
            tipo_input=tipo_input,
            fatores=tuple(resposta.fatores),
        )


class RepositorioAnalises(Protocol):
    async def registrar(self, registro: RegistroAnalise) -> uuid.UUID: ...


class RepositorioAnalisesPostgres:
    def __init__(self, fabrica_de_sessoes: async_sessionmaker[AsyncSession]) -> None:
        self._fabrica_de_sessoes = fabrica_de_sessoes

    async def registrar(self, registro: RegistroAnalise) -> uuid.UUID:
        """Grava a análise e todos os indicadores numa transação só (invariante 6).

        Se qualquer insert falhar, o `begin()` desfaz tudo: nunca análise sem indicador nem
        conjunto parcial.
        """
        analise = Analise(
            score_risco=registro.score,
            nivel_risco=registro.nivel_risco,
            tipo_input=registro.tipo_input,
            indicadores=[
                IndicadorRisco(
                    tipo=fator.tipo,
                    categoria=fator.categoria,
                    descricao=fator.descricao,
                    peso=fator.peso,
                )
                for fator in registro.fatores
            ],
        )
        async with self._fabrica_de_sessoes() as sessao, sessao.begin():
            sessao.add(analise)
        return analise.id
