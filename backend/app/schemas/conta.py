"""Contrato de /api/historico e /api/conta (ADR-0015).

O item do histórico traz a mensagem analisada enquanto ela existe no banco (ADR-0018). As URLs
não vêm: o banco não as guarda (ADR-0009), e elas continuam visíveis dentro do próprio texto.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.analise import ExplicacaoIA, NivelRisco, Orientacao


class FatorHistorico(BaseModel):
    categoria: str
    descricao: str = Field(description="Template do `regras.yaml` já renderizado (ADR-0004).")
    peso: int


class ItemHistorico(BaseModel):
    id: uuid.UUID
    created_at: datetime = Field(description="ISO 8601 com fuso; a tela converte para o local.")
    nivel_risco: NivelRisco
    score_risco: int
    fatores: list[FatorHistorico]
    texto: str | None = Field(
        description="A mensagem como foi colada. `null` nas análises anteriores ao ADR-0018."
    )
    # Campos aditivos da fatia 6 (ADR-0020): o histórico mostra a mesma resposta da home.
    orientacao: Orientacao = Field(description="A resposta fixa do nível guardado (plano B).")
    explicacao_ia: ExplicacaoIA | None = Field(
        description=(
            "O que a IA escreveu, quando ela entrou. `null` nas análises sem IA e nas "
            "anteriores ao ADR-0020: a tela mostra então o plano B."
        )
    )


class RespostaHistorico(BaseModel):
    dias: int = Field(description="Tamanho da janela, em dias (`HISTORICO_DIAS`).")
    analises: list[ItemHistorico] = Field(description="Mais recente primeiro; no máximo 200.")


class RespostaConta(BaseModel):
    """A seção "Meus dados". Sem id, sem hash de senha."""

    nome: str
    email: str
    criado_em: datetime
