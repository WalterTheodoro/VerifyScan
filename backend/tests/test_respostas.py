"""As respostas do plano B (ADR-0020): uma por nível, versionadas no `respostas.yaml`.

São o que a pessoa lê quando a IA está desligada, fora do ar, lenta ou respondeu algo inválido.
O sistema nunca diz "não é golpe": o algoritmo só sabe que não achou os sinais que conhece.
"""

import pytest
from pydantic import ValidationError

from app.analyzers.normalizacao import normalizar
from app.scoring.respostas import RespostasPadrao, carregar_respostas


def test_os_tres_niveis_com_os_titulos_combinados() -> None:
    respostas = carregar_respostas()

    assert respostas.para("BAIXO").titulo == "Não encontramos sinais comuns de golpe."
    assert respostas.para("MEDIO").titulo == "Esta mensagem tem sinais que aparecem em golpes."
    assert respostas.para("ALTO").titulo == "Esta mensagem tem fortes sinais de golpe."


def test_baixo_tem_texto_e_nao_tem_passos() -> None:
    baixo = carregar_respostas().para("BAIXO")

    assert baixo.texto is not None
    assert baixo.texto.startswith("Isso não garante que a mensagem seja segura.")
    assert baixo.passos == ()


@pytest.mark.parametrize("nivel", ["MEDIO", "ALTO"])
def test_medio_e_alto_tem_passos(nivel: str) -> None:
    resposta = carregar_respostas().para(nivel)  # type: ignore[arg-type]

    assert len(resposta.passos) >= 3


def test_alto_cita_o_med_e_o_prazo() -> None:
    passos = " ".join(carregar_respostas().para("ALTO").passos)

    assert "MED (Mecanismo Especial de Devolução, do Banco Central)" in passos
    assert "80 dias" in passos
    assert "boletim de ocorrência" in passos


def test_nenhum_texto_afirma_que_nao_e_golpe() -> None:
    respostas = carregar_respostas()
    for nivel in ("BAIXO", "MEDIO", "ALTO"):
        resposta = respostas.para(nivel)  # type: ignore[arg-type]
        tudo = normalizar(" ".join([resposta.titulo, resposta.texto or "", *resposta.passos]))
        assert "nao e golpe" not in tudo
        assert "e seguro" not in tudo
        assert "e segura" not in tudo


def _validas() -> dict[str, object]:
    return {
        "versao": 1,
        "niveis": {
            "BAIXO": {"titulo": "t", "texto": "x"},
            "MEDIO": {"titulo": "t", "passos": ["a", "b"]},
            "ALTO": {"titulo": "t", "passos": ["a", "b"]},
        },
    }


def test_nivel_faltando_derruba_o_boot() -> None:
    dados = _validas()
    del dados["niveis"]["ALTO"]  # type: ignore[attr-defined]

    with pytest.raises(ValidationError, match="ALTO"):
        RespostasPadrao.model_validate(dados)


def test_resposta_sem_texto_nem_passos_derruba_o_boot() -> None:
    dados = _validas()
    dados["niveis"]["MEDIO"] = {"titulo": "t"}  # type: ignore[index]

    with pytest.raises(ValidationError):
        RespostasPadrao.model_validate(dados)
