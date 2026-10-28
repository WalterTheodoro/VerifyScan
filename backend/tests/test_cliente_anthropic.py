"""O adaptador do SDK da Anthropic, com o SDK de verdade sobre um transporte falso (ADR-0020).

Nenhum byte sai da máquina: o `MockTransport` responde no lugar da API. Isso prova o que um
falso do `ClienteIA` não provaria — o formato do pedido que o SDK monta e a leitura da resposta.
"""

import json
import logging
from collections.abc import Callable

import httpx2
import pytest
from anthropic import AsyncAnthropic, DefaultAsyncHttpxClient

from app.formulator.cliente import ClienteAnthropic, criar_cliente_ia
from app.formulator.saida import SCHEMA_SAIDA
from tests.conftest import settings_de_teste

CHAVE = "sk-ant-teste-NAO-E-CHAVE-REAL-456"
MENSAGEM_SECRETA = "MENSAGEM-QUE-NAO-PODE-IR-PARA-O-LOG"
SAIDA = '{"tipo": "x", "sinais": [], "nivel_sugerido": "BAIXO", "o_que_fazer": ["a", "b"]}'


def _mensagem(
    conteudo: list[dict[str, object]], stop_reason: str = "end_turn"
) -> dict[str, object]:
    return {
        "id": "msg_teste",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-5-5",
        "content": conteudo,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 1234, "output_tokens": 321},
    }


def _cliente(
    responder: Callable[[httpx2.Request], httpx2.Response],
) -> ClienteAnthropic:
    sdk = AsyncAnthropic(
        api_key=CHAVE,
        max_retries=0,
        http_client=DefaultAsyncHttpxClient(transport=httpx2.MockTransport(responder)),
    )
    return ClienteAnthropic(sdk, modelo="claude-haiku-5-5", max_tokens=700)


async def test_monta_o_pedido_e_le_a_resposta() -> None:
    pedidos: list[httpx2.Request] = []

    def responder(pedido: httpx2.Request) -> httpx2.Response:
        pedidos.append(pedido)
        return httpx2.Response(200, json=_mensagem([{"type": "text", "text": SAIDA}]))

    resposta = await _cliente(responder).gerar("SISTEMA", "ENTRADA")

    assert resposta.texto == SAIDA
    assert resposta.motivo_parada == "end_turn"
    assert resposta.modelo == "claude-haiku-5-5"
    assert (resposta.tokens_entrada, resposta.tokens_saida) == (1234, 321)

    corpo = json.loads(pedidos[0].content)
    assert corpo["model"] == "claude-haiku-5-5"
    assert corpo["max_tokens"] == 700
    assert corpo["system"] == "SISTEMA"
    assert corpo["messages"] == [{"role": "user", "content": "ENTRADA"}]
    # Pensamento desligado: no Haiku 5.5 ele vem ligado e consumiria o teto de 700 tokens.
    assert corpo["thinking"] == {"type": "disabled"}
    assert corpo["output_config"]["format"] == {"type": "json_schema", "schema": SCHEMA_SAIDA}
    assert "temperature" not in corpo


async def test_le_o_bloco_de_texto_pelo_tipo() -> None:
    """Uma resposta pode começar por um bloco de pensamento; o JSON está no bloco `text`."""

    def responder(pedido: httpx2.Request) -> httpx2.Response:
        conteudo = [
            {"type": "thinking", "thinking": "", "signature": "assinatura"},
            {"type": "text", "text": SAIDA},
        ]
        return httpx2.Response(200, json=_mensagem(conteudo))

    assert (await _cliente(responder).gerar("S", "E")).texto == SAIDA


async def test_recusa_vem_com_o_motivo() -> None:
    def responder(pedido: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=_mensagem([], stop_reason="refusal"))

    resposta = await _cliente(responder).gerar("S", "E")

    assert resposta.motivo_parada == "refusal"
    assert resposta.texto == ""


async def test_nem_a_chave_nem_a_mensagem_vao_para_o_log(caplog: pytest.LogCaptureFixture) -> None:
    """Em DEBUG, o SDK escreveria as opções do pedido — com a mensagem — no log. O módulo do
    cliente fixa o logger `anthropic` em WARNING; este teste liga DEBUG em tudo o resto."""

    def responder(pedido: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=_mensagem([{"type": "text", "text": SAIDA}]))

    with caplog.at_level(logging.DEBUG):
        await _cliente(responder).gerar("S", MENSAGEM_SECRETA)

    assert CHAVE not in caplog.text
    assert MENSAGEM_SECRETA not in caplog.text


def test_ia_desligada_nao_cria_cliente() -> None:
    assert criar_cliente_ia(settings_de_teste()) is None


def test_ia_ligada_cria_cliente_sem_retry() -> None:
    """Sem nova tentativa: o teto de 15 s é da chamada inteira (ADR-0020)."""
    cliente = criar_cliente_ia(
        settings_de_teste(ia_ativada=True, anthropic_api_key=CHAVE, ia_timeout_s=7)
    )

    assert isinstance(cliente, ClienteAnthropic)
    assert cliente.sdk.max_retries == 0
    assert cliente.sdk.timeout == 7


async def test_leitura_manda_a_imagem_antes_do_texto() -> None:
    """Fatia 9 (ADR-0023): a documentação recomenda a imagem antes do texto. O teto de tokens é o
    da leitura, e o schema é o que veio — o de leitura, não o da análise."""
    import base64

    from app.ocr.leitura import PROMPT_LEITURA, SCHEMA_LEITURA

    pedidos: list[httpx2.Request] = []

    def responder(pedido: httpx2.Request) -> httpx2.Response:
        pedidos.append(pedido)
        return httpx2.Response(200, json=_mensagem([{"type": "text", "text": "{}"}]))

    sdk = AsyncAnthropic(
        api_key=CHAVE,
        max_retries=0,
        http_client=DefaultAsyncHttpxClient(transport=httpx2.MockTransport(responder)),
    )
    cliente = ClienteAnthropic(
        sdk, modelo="claude-haiku-5-5", max_tokens=700, max_tokens_leitura=2500
    )
    jpeg = b"\xff\xd8\xff-bytes-do-print"
    resposta = await cliente.ler(PROMPT_LEITURA, jpeg, SCHEMA_LEITURA)

    assert (resposta.tokens_entrada, resposta.tokens_saida) == (1234, 321)
    corpo = json.loads(pedidos[0].content)
    assert corpo["max_tokens"] == 2500
    assert corpo["system"] == PROMPT_LEITURA
    imagem, texto = corpo["messages"][0]["content"]
    assert imagem == {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": base64.standard_b64encode(jpeg).decode(),
        },
    }
    assert texto == {"type": "text", "text": "Leia o print acima."}
    assert corpo["thinking"] == {"type": "disabled"}
    assert corpo["output_config"]["format"] == {"type": "json_schema", "schema": SCHEMA_LEITURA}
    assert "temperature" not in corpo
