"""A chamada ao Claude, atrás de uma interface (CLAUDE.md §6): `ClienteIA` (análise) e
`ClienteLeitura` (leitura do print, ADR-0023) são os Protocols, o `ClienteAnthropic` fala com a API
e os testes usam falsos determinísticos.

O adaptador é fino de propósito: monta o pedido, devolve o texto e os números. Quem decide o
que fazer com a resposta — validar, limpar, cair no plano B — é o `AnalisadorIA`.
"""

import base64
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from anthropic import AsyncAnthropic
from anthropic.types import Message

from app.core.config import Settings
from app.formulator.saida import SCHEMA_SAIDA

# Em DEBUG, o SDK escreve no log as opções de cada pedido, e elas trazem a mensagem do usuário.
# Fixar o logger dele em WARNING mantém a regra "nunca o texto no log" mesmo com DEBUG ligado
# no resto (o mesmo cuidado do `hide_parameters=True` do engine, ADR-0018).
logging.getLogger("anthropic").setLevel(logging.WARNING)


@dataclass(frozen=True)
class RespostaIA:
    """O que volta da API: o texto (o JSON pedido), por que parou e quanto custou."""

    texto: str
    motivo_parada: str
    modelo: str
    tokens_entrada: int
    tokens_saida: int


class ClienteIA(Protocol):
    async def gerar(self, sistema: str, entrada: str) -> RespostaIA: ...


class ClienteLeitura(Protocol):
    async def ler(self, sistema: str, jpeg: bytes, schema: dict[str, Any]) -> RespostaIA: ...


class ClienteAnthropic:
    def __init__(
        self,
        sdk: AsyncAnthropic,
        modelo: str,
        max_tokens: int,
        max_tokens_leitura: int = 2500,
    ) -> None:
        self.sdk = sdk
        self._modelo = modelo
        self._max_tokens = max_tokens
        self._max_tokens_leitura = max_tokens_leitura

    async def gerar(self, sistema: str, entrada: str) -> RespostaIA:
        """Uma chamada à Messages API, com saída estruturada (`output_config.format`).

        Pensamento desligado: no Haiku 5.5 ele vem ligado por padrão e conta no `max_tokens` —
        com 700 tokens, poderia não sobrar espaço para o JSON. Sem `temperature`, que o Haiku 5.5
        recusa com 400.
        """
        resposta = await self.sdk.messages.create(
            model=self._modelo,
            max_tokens=self._max_tokens,
            system=sistema,
            messages=[{"role": "user", "content": entrada}],
            thinking={"type": "disabled"},
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": SCHEMA_SAIDA},
            },
        )
        return _resposta(resposta)

    async def ler(self, sistema: str, jpeg: bytes, schema: dict[str, Any]) -> RespostaIA:
        """A leitura do print: a imagem e depois uma frase curta, como a documentação recomenda
        (imagem antes do texto). Mesmas escolhas do `gerar`; o teto de tokens é o da leitura,
        porque a transcrição pode ter alguns milhares de caracteres."""
        resposta = await self.sdk.messages.create(
            model=self._modelo,
            max_tokens=self._max_tokens_leitura,
            system=sistema,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64.standard_b64encode(jpeg).decode("ascii"),
                            },
                        },
                        {"type": "text", "text": "Leia o print acima."},
                    ],
                }
            ],
            thinking={"type": "disabled"},
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
        )
        return _resposta(resposta)


def _resposta(resposta: Message) -> RespostaIA:
    # Pelo tipo do bloco, nunca pela posição: uma resposta pode começar por pensamento.
    texto = "".join(bloco.text for bloco in resposta.content if bloco.type == "text")
    return RespostaIA(
        texto=texto,
        motivo_parada=resposta.stop_reason or "",
        modelo=resposta.model,
        tokens_entrada=resposta.usage.input_tokens,
        tokens_saida=resposta.usage.output_tokens,
    )


def criar_cliente_ia(settings: Settings) -> ClienteAnthropic | None:
    """O cliente real, ou `None` com a IA desligada.

    Sem nova tentativa (`max_retries=0`): o teto de `ia_timeout_s` é da chamada inteira, e uma
    segunda tentativa estouraria o orçamento da invariante 8.
    """
    if not settings.ia_ativada or settings.anthropic_api_key is None:
        return None
    sdk = AsyncAnthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
        timeout=settings.ia_timeout_s,
        max_retries=0,
    )
    return ClienteAnthropic(
        sdk,
        modelo=settings.ia_modelo,
        max_tokens=settings.ia_max_tokens,
        max_tokens_leitura=settings.ia_max_tokens_leitura,
    )
