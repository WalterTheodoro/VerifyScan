"""A regra fixa de combinação (ADR-0020): o nível final é o maior entre o do motor e o da IA.

A IA pode subir o nível, nunca baixar. É a defesa contra prompt injection (OWASP LLM01): uma
mensagem que convença o modelo de que é segura não apaga o que o motor já encontrou.
"""

import pytest

from app.schemas.analise import NivelRisco
from app.scoring.combinacao import combinar

AS_NOVE = [
    ("BAIXO", "BAIXO", "BAIXO"),
    ("BAIXO", "MEDIO", "MEDIO"),
    ("BAIXO", "ALTO", "ALTO"),
    ("MEDIO", "BAIXO", "MEDIO"),
    ("MEDIO", "MEDIO", "MEDIO"),
    ("MEDIO", "ALTO", "ALTO"),
    ("ALTO", "BAIXO", "ALTO"),
    ("ALTO", "MEDIO", "ALTO"),
    ("ALTO", "ALTO", "ALTO"),
]


@pytest.mark.parametrize(("motor", "ia", "esperado"), AS_NOVE)
def test_as_nove_combinacoes(motor: NivelRisco, ia: NivelRisco, esperado: NivelRisco) -> None:
    assert combinar(motor, ia) == esperado


def test_motor_medio_e_ia_baixo_fica_medio() -> None:
    """O caso que a banca vai perguntar: a IA disse BAIXO, o motor achou sinais. Fica MEDIO."""
    assert combinar("MEDIO", "BAIXO") == "MEDIO"


@pytest.mark.parametrize("motor", ["BAIXO", "MEDIO", "ALTO"])
def test_sem_ia_vale_o_motor(motor: NivelRisco) -> None:
    assert combinar(motor, None) == motor
