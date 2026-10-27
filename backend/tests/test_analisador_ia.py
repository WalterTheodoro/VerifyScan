"""O `AnalisadorIA`: uma chamada, um teto, e plano B em qualquer falha (ADR-0020).

A análise nunca falha por causa da IA (invariante 3). Timeout, erro da API, JSON inválido,
recusa e resposta cortada viram `None`, e o orquestrador responde só com o motor.
"""

import logging

import anthropic
import httpx2
import pytest

from app.formulator.analisador import AnalisadorIA
from app.formulator.prompt import PROMPT_SISTEMA, EntradaIA
from app.schemas.analise import Fator
from tests.conftest import ClienteIAFalso, saida_da_ia

MENSAGEM = "Seu pacote está retido nos Correios. Pague a taxa de R$ 9,90 hoje pelo PIX."
ENTRADA = EntradaIA(
    mensagem=MENSAGEM,
    nivel_motor="BAIXO",
    fatores=(
        Fator(
            tipo="texto",
            categoria="solicitacao_financeira",
            descricao="A mensagem pede pagamento.",
            peso=25,
        ),
    ),
    urls=(),
)
PEDIDO = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
CHAVE = "sk-ant-teste-NAO-E-CHAVE-REAL-789"


async def test_desligada_nao_chama_nada_e_nao_loga(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        assert await AnalisadorIA(None, timeout_s=15).avaliar(ENTRADA) is None

    assert not [r for r in caplog.records if r.name.startswith("app.formulator")]


async def test_sucesso_devolve_nivel_e_explicacao() -> None:
    cliente = ClienteIAFalso(saida_da_ia(nivel_sugerido="ALTO"))

    resultado = await AnalisadorIA(cliente, timeout_s=15).avaliar(ENTRADA)

    assert resultado is not None
    assert resultado.nivel_sugerido == "ALTO"
    assert resultado.modelo == "claude-haiku-5-5"
    assert resultado.explicacao.tipo == "falsa cobrança de taxa dos Correios"
    sistema, entrada = cliente.chamadas[0]
    assert sistema == PROMPT_SISTEMA
    assert MENSAGEM in entrada
    assert "nivel: BAIXO" in entrada


async def test_nivel_com_outra_caixa_e_aceito() -> None:
    cliente = ClienteIAFalso(saida_da_ia(nivel_sugerido="medio"))

    resultado = await AnalisadorIA(cliente, timeout_s=15).avaliar(ENTRADA)

    assert resultado is not None
    assert resultado.nivel_sugerido == "MEDIO"


async def test_explicacao_sai_sem_o_link_do_golpe() -> None:
    cliente = ClienteIAFalso(
        saida_da_ia(sinais=["O link correios-taxa.com.br/pagar imita os Correios."])
    )

    resultado = await AnalisadorIA(cliente, timeout_s=15).avaliar(ENTRADA)

    assert resultado is not None
    assert resultado.explicacao.sinais == ("O link [link removido] imita os Correios.",)


async def test_timeout_e_plano_b(caplog: pytest.LogCaptureFixture) -> None:
    cliente = ClienteIAFalso(saida_da_ia(), demora_s=1.0)

    with caplog.at_level(logging.WARNING):
        assert await AnalisadorIA(cliente, timeout_s=0.05).avaliar(ENTRADA) is None

    [registro] = caplog.records
    assert registro.levelno == logging.WARNING
    assert "TimeoutError" in registro.getMessage()


@pytest.mark.parametrize(
    "erro",
    [
        anthropic.APIConnectionError(request=PEDIDO),
        anthropic.APITimeoutError(request=PEDIDO),
        anthropic.InternalServerError(
            "erro", response=httpx2.Response(500, request=PEDIDO), body=None
        ),
        anthropic.RateLimitError("erro", response=httpx2.Response(429, request=PEDIDO), body=None),
        anthropic.AuthenticationError(
            "erro", response=httpx2.Response(401, request=PEDIDO), body=None
        ),
    ],
    ids=lambda erro: type(erro).__name__,
)
async def test_erro_da_api_e_plano_b(erro: Exception, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        assert await AnalisadorIA(ClienteIAFalso(erro=erro), timeout_s=15).avaliar(ENTRADA) is None

    assert type(erro).__name__ in caplog.text


@pytest.mark.parametrize(
    ("texto", "motivo"),
    [
        ("isso não é JSON", "ValidationError"),
        (saida_da_ia(sinais=["a", "b", "c", "d", "e", "f"]), "ValidationError"),
        (saida_da_ia(o_que_fazer=["só um"]), "ValidationError"),
        (saida_da_ia(nivel_sugerido="PERIGO"), "ValidationError"),
        (saida_da_ia(sinais=["Esta mensagem é segura."]), "SaidaInutilizavel"),
    ],
    ids=["nao-json", "6-sinais", "1-passo", "nivel", "afirma-seguranca"],
)
async def test_saida_invalida_e_plano_b(
    texto: str, motivo: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        assert await AnalisadorIA(ClienteIAFalso(texto), timeout_s=15).avaliar(ENTRADA) is None

    assert motivo in caplog.text


@pytest.mark.parametrize(
    ("motivo_parada", "motivo"), [("refusal", "SaidaRecusada"), ("max_tokens", "SaidaCortada")]
)
async def test_recusa_e_resposta_cortada_sao_plano_b(
    motivo_parada: str, motivo: str, caplog: pytest.LogCaptureFixture
) -> None:
    cliente = ClienteIAFalso(saida_da_ia(), motivo_parada=motivo_parada)

    with caplog.at_level(logging.WARNING):
        assert await AnalisadorIA(cliente, timeout_s=15).avaliar(ENTRADA) is None

    assert motivo in caplog.text


async def test_sucesso_loga_latencia_e_tokens(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="app.formulator"):
        await AnalisadorIA(ClienteIAFalso(saida_da_ia()), timeout_s=15).avaliar(ENTRADA)

    [registro] = caplog.records
    assert registro.levelno == logging.INFO
    assert "ms" in registro.getMessage()
    assert "1000 tokens de entrada" in registro.getMessage()
    assert "200 de saída" in registro.getMessage()


@pytest.mark.parametrize("falha", [False, True], ids=["sucesso", "plano-b"])
async def test_nem_a_mensagem_nem_a_saida_vao_para_o_log(
    falha: bool, caplog: pytest.LogCaptureFixture
) -> None:
    """A saída da IA pode citar a mensagem: nenhuma das duas vai para o log, em nível nenhum."""
    texto_da_ia = saida_da_ia(tipo="TIPO-QUE-NAO-PODE-IR-PARA-O-LOG")
    if falha:
        texto_da_ia = texto_da_ia.replace('"BAIXO"', '"PERIGO"').replace('"ALTO"', '"PERIGO"')

    with caplog.at_level(logging.DEBUG):
        await AnalisadorIA(ClienteIAFalso(texto_da_ia), timeout_s=15).avaliar(ENTRADA)

    assert caplog.records
    assert "Correios" not in caplog.text
    assert "TIPO-QUE-NAO-PODE-IR-PARA-O-LOG" not in caplog.text
    assert "9,90" not in caplog.text


async def test_erro_com_a_chave_na_mensagem_nao_vaza(caplog: pytest.LogCaptureFixture) -> None:
    """O log leva o tipo da exceção, nunca o texto dela — que pode ter vindo do servidor."""
    cliente = ClienteIAFalso(erro=RuntimeError(f"falhou com a chave {CHAVE}"))

    with caplog.at_level(logging.DEBUG):
        assert await AnalisadorIA(cliente, timeout_s=15).avaliar(ENTRADA) is None

    assert CHAVE not in caplog.text
    assert "RuntimeError" in caplog.text
