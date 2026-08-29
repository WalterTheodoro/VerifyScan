"""ScoringEngine — agrega os fatores, soma o score e classifica o nível (§5.4.7 do RFC)."""

import pytest

from app.schemas.analise import CategoriaFator, Fator, NivelRisco
from app.scoring.motor import ScoringEngine
from app.scoring.regras import carregar_regras


@pytest.fixture
def motor() -> ScoringEngine:
    return ScoringEngine(carregar_regras())


def fator(categoria: CategoriaFator, peso: int) -> Fator:
    return Fator(tipo="texto", categoria=categoria, descricao="Descrição.", peso=peso)


def test_sem_fator_o_score_e_zero_e_o_risco_e_baixo(motor: ScoringEngine) -> None:
    resultado = motor.pontuar([])

    assert resultado.score == 0
    assert resultado.nivel_risco == "BAIXO"
    assert resultado.fatores == []


def test_soma_os_pesos_de_categorias_diferentes(motor: ScoringEngine) -> None:
    resultado = motor.pontuar([fator("urgencia", 10), fator("solicitacao_financeira", 25)])

    assert resultado.score == 35
    assert len(resultado.fatores) == 2


def test_categoria_repetida_pontua_uma_vez_so(motor: ScoringEngine) -> None:
    """ADR-0004: agregação por categoria. Duas URLs com o mesmo problema não dobram o score."""
    resultado = motor.pontuar([fator("urgencia", 10), fator("urgencia", 10)])

    assert resultado.score == 10
    assert len(resultado.fatores) == 1


def test_preserva_a_ordem_de_chegada_dos_fatores(motor: ScoringEngine) -> None:
    entrada = [fator("dados_pessoais", 25), fator("urgencia", 10), fator("dados_pessoais", 25)]

    resultado = motor.pontuar(entrada)

    assert [f.categoria for f in resultado.fatores] == ["dados_pessoais", "urgencia"]


# ─── faixas: §5.4.7, 0-30 BAIXO · 31-60 MÉDIO · 61+ ALTO ──────────────────────────────────
# As fronteiras são o que a Fase 2 vai recalibrar (ADR-0005); por isso estão testadas uma a
# uma, e não só "um caso de cada nível".


@pytest.mark.parametrize(
    ("score", "esperado"),
    [
        (0, "BAIXO"),
        (30, "BAIXO"),
        (31, "MEDIO"),
        (60, "MEDIO"),
        (61, "ALTO"),
        (110, "ALTO"),
    ],
)
def test_fronteiras_das_faixas(score: int, esperado: NivelRisco) -> None:
    assert carregar_regras().faixas.classificar(score) == esperado


def test_as_seis_categorias_juntas_dao_alto(motor: ScoringEngine) -> None:
    """Teto do texto puro: 10+15+15+20+25+25 = 110 (§5.4.1)."""
    regras = carregar_regras()

    resultado = motor.pontuar(
        [fator(categoria.id, categoria.peso) for categoria in regras.categorias]
    )

    assert resultado.score == 110
    assert resultado.nivel_risco == "ALTO"
