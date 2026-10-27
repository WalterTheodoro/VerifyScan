"""Carregamento e validação do `scoring/respostas.yaml`, as respostas do plano B (ADR-0020).

Mesmo contrato do `regras.yaml` (ADR-0008): o texto é dado versionado, e um arquivo quebrado
derruba o boot, não a primeira análise.
"""

from functools import lru_cache
from pathlib import Path
from typing import Self, get_args

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.analise import NivelRisco, Orientacao

CAMINHO_RESPOSTAS = Path(__file__).parent / "respostas.yaml"

NIVEIS: tuple[NivelRisco, ...] = get_args(NivelRisco)


class RespostasPadrao(BaseModel):
    """O `respostas.yaml` inteiro, validado: exatamente uma resposta para cada nível."""

    model_config = ConfigDict(frozen=True)

    versao: int = Field(ge=1)
    niveis: dict[NivelRisco, Orientacao]

    @model_validator(mode="after")
    def _um_por_nivel(self) -> Self:
        faltando = [nivel for nivel in NIVEIS if nivel not in self.niveis]
        if faltando:
            raise ValueError(f"níveis sem resposta no respostas.yaml: {faltando}")
        return self

    def para(self, nivel: NivelRisco) -> Orientacao:
        return self.niveis[nivel]


@lru_cache
def carregar_respostas() -> RespostasPadrao:
    """Lê e valida o `respostas.yaml`. Chamado em `criar_app()` para que o erro apareça no boot."""
    with CAMINHO_RESPOSTAS.open(encoding="utf-8") as arquivo:
        return RespostasPadrao.model_validate(yaml.safe_load(arquivo))
