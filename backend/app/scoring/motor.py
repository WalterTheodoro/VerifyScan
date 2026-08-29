"""ScoringEngine — agrega os fatores de todos os analisadores e classifica o risco (§5.4.7).

Nesta fase só chegam fatores de texto. A partir da Fase 3 chegam também os de domínio e
reputação, e é por isso que a agregação vive aqui e não dentro de cada analisador: nenhum
deles enxerga o conjunto completo.
"""

from collections.abc import Iterable
from typing import assert_never

from pydantic import BaseModel

from app.schemas.analise import CategoriaFator, Fator, NivelRisco
from app.scoring.regras import Regras


class ResultadoPontuacao(BaseModel):
    """O que o motor devolve: score, nível e os fatores que efetivamente pontuaram."""

    score: int
    nivel_risco: NivelRisco
    fatores: list[Fator]


class ScoringEngine:
    def __init__(self, regras: Regras) -> None:
        self._faixas = regras.faixas
        self._agregacao = regras.agregacao

    def pontuar(self, fatores: Iterable[Fator]) -> ResultadoPontuacao:
        if self._agregacao == "por_categoria":
            considerados = _um_por_categoria(fatores)
        else:
            # Se um novo modo de agregação entrar no Literal do `regras.yaml`, o mypy exige
            # que ele seja tratado aqui em vez de cair silenciosamente no comportamento antigo.
            assert_never(self._agregacao)

        score = sum(fator.peso for fator in considerados)
        return ResultadoPontuacao(
            score=score,
            nivel_risco=self._faixas.classificar(score),
            fatores=considerados,
        )


def _um_por_categoria(fatores: Iterable[Fator]) -> list[Fator]:
    """Mantém o primeiro fator de cada categoria, na ordem de chegada (ADR-0004).

    Todos os fatores de uma categoria carregam o peso dela, então qual deles sobrevive não
    muda o score — só a descrição exibida, e a primeira é a que o usuário leria de qualquer
    forma. Somar por ocorrência criaria viés de comprimento: texto longo ficaria
    automaticamente mais perigoso.
    """
    vistos: dict[CategoriaFator, Fator] = {}
    for fator in fatores:
        vistos.setdefault(fator.categoria, fator)
    return list(vistos.values())
