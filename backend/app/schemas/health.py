"""Contrato de `GET /health`."""

from typing import Literal

from pydantic import BaseModel, Field

StatusServico = Literal["ok", "erro"]
StatusGeral = Literal["ok", "degradado"]


class SaudeServico(BaseModel):
    """Resultado da checagem de uma dependência de infraestrutura."""

    status: StatusServico
    latencia_ms: float = Field(description="Tempo da checagem, incluindo a falha quando houver.")
    detalhe: str | None = Field(
        default=None,
        description="Preenchido apenas quando `status` é 'erro'. Tipo da exceção e mensagem curta.",
    )


class RespostaHealth(BaseModel):
    """Estado da API e de cada dependência, separadamente.

    `status` é 'degradado' se qualquer serviço falhar; nesse caso a resposta sai com HTTP 503,
    mantendo o mesmo formato de corpo.
    """

    status: StatusGeral
    postgres: SaudeServico
    redis: SaudeServico
