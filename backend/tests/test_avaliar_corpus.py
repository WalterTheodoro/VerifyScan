"""Testes do `tools/avaliar_corpus.py`: Wilson, matriz, métricas, baseline trivial e o gate.

O gate de regressão roda o motor de verdade sobre a calibração do corpus e compara com a linha de
base gravada. Só a calibração: o CI faz parte do ciclo de ajuste, e mostrar o teste a ele seria
ajustar contra o teste (ADR-0021).
"""

import json
from pathlib import Path

import pytest

from app.analyzers.urls import URLExtractor
from app.api.deps import obter_servico_analise
from app.scoring.regras import carregar_regras
from tools.avaliar_corpus import (
    LINHA_DE_BASE,
    PASTA_CASOS,
    Avaliacao,
    Carimbo,
    Caso,
    Proporcao,
    Resultado,
    avaliar,
    calcular_metricas,
    carregar_corpus,
    classificar_trivial,
    comparar_com_linha_de_base,
    hash_do_corpus,
    linha_de_base,
    matriz,
    montar_relatorio,
    percentil,
    wilson,
)


def _resultado(id_caso: str, rotulo: str, nivel: str) -> Resultado:
    return Resultado(id=id_caso, rotulo=rotulo, autor="claude", divisao="calibracao", nivel=nivel)  # type: ignore[arg-type]


def _resultados(golpes: list[str], legitimas: list[str]) -> list[Resultado]:
    return [_resultado(f"g{i}", "golpe", nivel) for i, nivel in enumerate(golpes)] + [
        _resultado(f"l{i}", "legitimo", nivel) for i, nivel in enumerate(legitimas)
    ]


# ── Wilson ───────────────────────────────────────────────────────────────────────────────────


def test_wilson_de_cinco_em_dez():
    baixo, alto = wilson(5, 10)
    assert baixo == pytest.approx(0.2366, abs=1e-4)
    assert alto == pytest.approx(0.7634, abs=1e-4)


def test_wilson_nos_extremos_nao_sai_de_zero_a_um():
    # O intervalo normal daria [0, 0] para 0/10 — "certeza" com dez casos. Wilson não.
    assert wilson(0, 10) == pytest.approx((0.0, 0.2775), abs=1e-4)
    assert wilson(10, 10) == pytest.approx((0.7225, 1.0), abs=1e-4)


def test_wilson_sem_casos_e_erro():
    with pytest.raises(ValueError):
        wilson(0, 0)


def test_proporcao_sem_casos_nao_tem_valor():
    assert Proporcao(0, 0).valor is None
    assert Proporcao(0, 0).intervalo is None
    assert "sem casos" in Proporcao(0, 0).formatar()


def test_proporcao_formata_em_portugues():
    assert Proporcao(5, 10).formatar() == "5/10 = 50,0% (IC 95%: 23,7% a 76,3%)"


# ── Matriz e métricas ────────────────────────────────────────────────────────────────────────


def test_matriz_conta_nivel_por_rotulo():
    contagem = matriz(_resultados(["ALTO", "ALTO", "MEDIO"], ["BAIXO", "MEDIO"]))
    assert contagem == {
        "BAIXO": {"golpe": 0, "legitimo": 1},
        "MEDIO": {"golpe": 1, "legitimo": 1},
        "ALTO": {"golpe": 2, "legitimo": 0},
    }


def test_metricas_com_medio_contando_como_golpe_e_a_variante():
    m = calcular_metricas(
        _resultados(["ALTO", "ALTO", "MEDIO", "BAIXO"], ["BAIXO", "BAIXO", "MEDIO", "ALTO"])
    )
    assert m.golpes_medio_ou_mais == Proporcao(3, 4)
    assert m.golpes_alto == Proporcao(2, 4)
    assert m.alarme_medio_ou_mais == Proporcao(2, 4)
    assert m.alarme_alto == Proporcao(1, 4)
    # Principal (ADR-0005): MÉDIO = golpe. VP 3, FP 2, FN 1, VN 2.
    assert m.precisao == Proporcao(3, 5)
    assert m.recall == Proporcao(3, 4)
    assert m.acuracia == Proporcao(5, 8)
    assert m.f1 == pytest.approx(2 * 0.6 * 0.75 / 1.35)
    # Variante: MÉDIO = legítimo. VP 2, FP 1, FN 2, VN 3.
    assert m.precisao_so_alto == Proporcao(2, 3)
    assert m.recall_so_alto == Proporcao(2, 4)
    assert m.acuracia_so_alto == Proporcao(5, 8)


def test_precisao_sem_nenhum_positivo_nao_tem_valor():
    m = calcular_metricas(_resultados(["BAIXO"], ["BAIXO"]))
    assert m.precisao == Proporcao(0, 0)
    assert m.f1 is None
    assert m.kpi_atendido is False


def test_kpi_exige_precisao_e_recall_acima_de_85():
    # 17 de 20 golpes = 85% exato: não passa, a errata 14 diz "> 85%".
    no_limite = calcular_metricas(_resultados(["ALTO"] * 17 + ["BAIXO"] * 3, ["BAIXO"] * 20))
    assert no_limite.precisao == Proporcao(17, 17)
    assert no_limite.kpi_atendido is False

    acima = calcular_metricas(_resultados(["ALTO"] * 18 + ["BAIXO"] * 2, ["BAIXO"] * 20))
    assert acima.kpi_atendido is True

    # Recall alto não salva precisão baixa: alarmar tudo não atende.
    tudo_alto = calcular_metricas(_resultados(["ALTO"] * 20, ["ALTO"] * 20))
    assert tudo_alto.recall == Proporcao(20, 20)
    assert tudo_alto.kpi_atendido is False


def test_percentil_por_posicao():
    valores = list(range(1, 21))
    assert percentil(valores, 0.5) == 10
    assert percentil(valores, 0.95) == 19
    assert percentil([7], 0.95) == 7


# ── Baseline trivial ─────────────────────────────────────────────────────────────────────────


@pytest.fixture
def extrator() -> URLExtractor:
    return URLExtractor(carregar_regras().urls)


@pytest.mark.parametrize(
    ("texto", "nivel"),
    [
        ("Pague a taxa via PIX: https://correios-taxa.example/pagar", "ALTO"),
        ("Pague a taxa via Pix agora", "BAIXO"),
        ("Acompanhe o pedido em https://loja.example/pedido", "BAIXO"),
        ("Veja o pixel da câmera em https://loja.example/camera", "BAIXO"),
    ],
)
def test_baseline_trivial_e_link_mais_pix(extrator, texto, nivel):
    assert classificar_trivial(texto, extrator) == nivel


# ── Corpus, hash e relatório ─────────────────────────────────────────────────────────────────


def test_hash_do_corpus_ignora_o_fim_de_linha(tmp_path):
    lf = tmp_path / "lf"
    crlf = tmp_path / "crlf"
    lf.mkdir()
    crlf.mkdir()
    (lf / "0001-a.yaml").write_bytes(b"id: '0001'\nrotulo: golpe\n")
    (crlf / "0001-a.yaml").write_bytes(b"id: '0001'\r\nrotulo: golpe\r\n")
    assert hash_do_corpus(lf) == hash_do_corpus(crlf)

    (crlf / "0001-a.yaml").write_bytes(b"id: '0001'\r\nrotulo: legitimo\r\n")
    assert hash_do_corpus(lf) != hash_do_corpus(crlf)


def _carimbo() -> Carimbo:
    return Carimbo(
        quando="2026-10-27 10:00",
        modo="motor",
        versao_regras=3,
        baixo_ate=30,
        medio_ate=60,
        modelo_ia="não usado",
        commit="abc1234",
        hash_corpus="0" * 64,
        semente=20261027,
    )


def test_relatorio_lista_erros_so_pelo_id_e_nunca_o_texto():
    sentinela = "TEXTO-QUE-NAO-PODE-VAZAR"
    casos = [
        Caso(
            id="0001",
            conteudo=f"{sentinela} golpe",
            rotulo="golpe",
            autor="claude",
            divisao="calibracao",
        ),
        Caso(
            id="0002",
            conteudo=f"{sentinela} legítima",
            rotulo="legitimo",
            autor="claude",
            divisao="teste",
        ),
    ]
    # Classificador que erra os dois: golpe em BAIXO e legítima em ALTO.
    resultados = avaliar(casos, lambda texto: "BAIXO" if "golpe" in texto else "ALTO")

    relatorio = montar_relatorio(_carimbo(), [Avaliacao("Motor", resultados, listar_erros=True)])

    assert sentinela not in relatorio
    assert "0001" in relatorio
    assert "0002" in relatorio
    for campo in ("v3", "abc1234", "0" * 64, "20261027", "BAIXO ≤ 30", "não usado"):
        assert campo in relatorio


def test_relatorio_separa_por_autor():
    resultados = [
        Resultado(id="0001", rotulo="golpe", autor="claude", divisao="calibracao", nivel="ALTO"),
        Resultado(id="0002", rotulo="golpe", autor="walter", divisao="teste", nivel="BAIXO"),
    ]
    relatorio = montar_relatorio(_carimbo(), [Avaliacao("Motor", resultados, listar_erros=True)])
    assert "autor claude" in relatorio
    assert "autor walter" in relatorio


# ── Gate de regressão ────────────────────────────────────────────────────────────────────────


def _base() -> dict:
    return linha_de_base(
        _resultados(["ALTO"] * 8 + ["MEDIO"] * 4 + ["BAIXO"] * 3, ["BAIXO"] * 8 + ["MEDIO"] * 2),
        hash_corpus="h",
        versao_regras=3,
    )


def test_gate_aceita_o_mesmo_resultado_e_melhora():
    base = _base()
    assert comparar_com_linha_de_base(base, base) == []

    melhor = linha_de_base(
        _resultados(["ALTO"] * 15, ["BAIXO"] * 10), hash_corpus="h", versao_regras=4
    )
    assert comparar_com_linha_de_base(melhor, base) == []


def test_gate_tolera_um_caso_a_mais_de_erro_e_nunca_dois():
    base = _base()
    um_golpe_a_menos = linha_de_base(
        _resultados(["ALTO"] * 8 + ["MEDIO"] * 3 + ["BAIXO"] * 4, ["BAIXO"] * 8 + ["MEDIO"] * 2),
        hash_corpus="h",
        versao_regras=3,
    )
    assert comparar_com_linha_de_base(um_golpe_a_menos, base) == []

    dois_golpes_a_menos = linha_de_base(
        _resultados(["ALTO"] * 8 + ["MEDIO"] * 2 + ["BAIXO"] * 5, ["BAIXO"] * 8 + ["MEDIO"] * 2),
        hash_corpus="h",
        versao_regras=3,
    )
    falhas = comparar_com_linha_de_base(dois_golpes_a_menos, base)
    assert len(falhas) == 1
    assert "golpes_medio_ou_mais" in falhas[0]

    dois_alarmes_a_mais = linha_de_base(
        _resultados(["ALTO"] * 8 + ["MEDIO"] * 4 + ["BAIXO"] * 3, ["BAIXO"] * 6 + ["ALTO"] * 4),
        hash_corpus="h",
        versao_regras=3,
    )
    falhas = comparar_com_linha_de_base(dois_alarmes_a_mais, base)
    assert any("alarme_medio_ou_mais" in falha for falha in falhas)
    assert any("alarme_alto" in falha for falha in falhas)


def test_gate_recusa_corpus_diferente_da_linha_de_base():
    base = _base()
    outro = {**base, "hash_corpus": "outro"}
    falhas = comparar_com_linha_de_base(outro, base)
    assert len(falhas) == 1
    assert "--gravar-linha-de-base" in falhas[0]


def test_motor_nao_regrediu_na_calibracao():
    """O gate do CI. Falhou? Ou o motor piorou, ou o corpus mudou: no segundo caso, regrave com
    `--gravar-linha-de-base` e anote o antes e o depois no `docs/diario.md`."""
    base = json.loads(Path(LINHA_DE_BASE).read_text(encoding="utf-8"))
    servico = obter_servico_analise()
    calibracao = [caso for caso in carregar_corpus(PASTA_CASOS) if caso.divisao == "calibracao"]
    resultados = avaliar(calibracao, lambda texto: servico.analisar(texto).nivel_motor)

    atual = linha_de_base(
        resultados,
        hash_corpus=hash_do_corpus(PASTA_CASOS),
        versao_regras=carregar_regras().versao,
    )

    assert comparar_com_linha_de_base(atual, base) == []
