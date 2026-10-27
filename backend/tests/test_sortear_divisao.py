"""`tools/sortear_divisao.py` — a divisão calibracao/teste é sorteada uma vez só (ADR-0021)."""

from typing import Any

from tools.sortear_divisao import FRACAO_TESTE, sortear


def _casos(rotulo: str, quantidade: int, inicio: int = 0) -> list[dict[str, Any]]:
    return [{"id": f"{rotulo}-{inicio + i:03d}", "rotulo": rotulo} for i in range(quantidade)]


def test_cada_rotulo_manda_trinta_por_cento_para_o_teste() -> None:
    casos = _casos("golpe", 90) + _casos("legitimo", 60)

    divisao = sortear(casos, semente=1)

    teste = {rotulo: 0 for rotulo in ("golpe", "legitimo")}
    for caso in casos:
        if divisao[caso["id"]] == "teste":
            teste[caso["rotulo"]] += 1
    assert teste == {"golpe": round(FRACAO_TESTE * 90), "legitimo": round(FRACAO_TESTE * 60)}


def test_mesma_semente_mesmo_sorteio_e_semente_diferente_muda() -> None:
    casos = _casos("golpe", 40)

    assert sortear(casos, semente=7) == sortear(casos, semente=7)
    assert sortear(casos, semente=7) != sortear(casos, semente=8)


def test_grupo_cai_inteiro_do_mesmo_lado() -> None:
    casos = _casos("golpe", 30)
    for caso in casos[:6]:
        caso["grupo"] = "correios"

    for semente in range(20):
        divisao = sortear(casos, semente=semente)
        assert len({divisao[caso["id"]] for caso in casos[:6]}) == 1


def test_caso_ja_dividido_nunca_muda_e_nao_volta_no_resultado() -> None:
    casos = _casos("golpe", 10)
    casos[0]["divisao"] = "teste"

    divisao = sortear(casos, semente=3)

    assert casos[0]["id"] not in divisao
    assert len(divisao) == 9


def test_caso_novo_de_grupo_existente_segue_o_lado_do_grupo() -> None:
    antigo = {"id": "a", "rotulo": "golpe", "grupo": "g", "divisao": "calibracao"}
    novo = {"id": "b", "rotulo": "golpe", "grupo": "g"}

    assert sortear([antigo, novo], semente=0) == {"b": "calibracao"}
