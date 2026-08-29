"""Carregamento e validação do `scoring/regras.yaml` (invariante 5 do CLAUDE.md).

Peso, padrão e faixa são dado versionado. Mudar um peso não pode exigir mudar código — e, do
outro lado, um YAML quebrado precisa derrubar o boot, não a primeira requisição do usuário.
Por isso toda a validação (categorias presentes, pesos positivos, faixas ordenadas, regex
compilando) acontece aqui, no carregamento. Ver ADR-0008.
"""

import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self, get_args

import yaml
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.analyzers.normalizacao import normalizar
from app.schemas.analise import CategoriaFator, NivelRisco
from app.scoring.descricoes import ModeloDescricao

CAMINHO_REGRAS = Path(__file__).parent / "regras.yaml"

CATEGORIAS_DE_TEXTO: tuple[CategoriaFator, ...] = get_args(CategoriaFator)
"""As seis da §5.4.1. Nas Fases 3 e 4 entram categorias de domínio e reputação, e aí esta
tupla deixa de ser igual a `get_args(CategoriaFator)`."""

# `\D`, `\S`, `\W`, `\B` viram `\d`, `\s`, `\w`, `\b` ao passar pelo `.lower()` do normalizador —
# a regex continua compilando e passa a significar o oposto. Preferimos falhar no boot.
_CLASSE_MAIUSCULA = re.compile(r"\\[A-Z]")


def normalizar_padrao(padrao: object) -> object:
    """Passa o padrão pelo mesmo normalizador do texto.

    Recusa o que a normalização inverteria, em vez de normalizar e seguir em frente.
    """
    if not isinstance(padrao, str):
        return padrao
    if _CLASSE_MAIUSCULA.search(padrao):
        raise ValueError(
            f"padrão usa classe de regex maiúscula, que a normalização inverteria: {padrao!r}"
        )
    return normalizar(padrao)


PadraoNormalizado = Annotated[re.Pattern[str], BeforeValidator(normalizar_padrao)]
"""Escrito em português natural no YAML, normalizado e compilado no carregamento."""


class Faixas(BaseModel):
    """Cortes de classificação do score (§5.4.7 do RFC).

    São objeto de calibração na Fase 2 tanto quanto os pesos (ADR-0005), e o relatório de
    avaliação carimba os valores vigentes — daí eles serem dado, e não constante no código.
    """

    model_config = ConfigDict(frozen=True)

    baixo_ate: int = Field(gt=0)
    medio_ate: int = Field(gt=0)

    @model_validator(mode="after")
    def _ordenadas(self) -> Self:
        if self.baixo_ate >= self.medio_ate:
            raise ValueError(
                f"faixa de BAIXO (até {self.baixo_ate}) precisa terminar antes da de MÉDIO "
                f"(até {self.medio_ate})"
            )
        return self

    def classificar(self, score: int) -> NivelRisco:
        if score <= self.baixo_ate:
            return "BAIXO"
        if score <= self.medio_ate:
            return "MEDIO"
        return "ALTO"


class ConfiguracaoURLs(BaseModel):
    """Configuração da extração de links (§5.4.2). Não tem peso: extrair não pontua.

    `tlds_conhecidos` só governa host escrito sem protocolo. Sem essa lista, qualquer
    `palavra.palavra` viraria link — "relatorio.final", "Obrigado.Att". Com `http://`
    explícito não há ambiguidade e a lista não se aplica.
    """

    model_config = ConfigDict(frozen=True)

    maximo_por_analise: int = Field(gt=0)
    tlds_conhecidos: frozenset[str] = Field(min_length=1)

    @field_validator("tlds_conhecidos")
    @classmethod
    def _minusculos_e_sem_ponto(cls, tlds: frozenset[str]) -> frozenset[str]:
        invalidos = sorted(tld for tld in tlds if not tld.isalnum() or tld != tld.lower())
        if invalidos:
            raise ValueError(f"TLD deve ser alfanumérico e minúsculo, sem ponto: {invalidos}")
        return tlds


class CategoriaTexto(BaseModel):
    """Uma das seis categorias da §5.4.1: peso, descrição e os padrões que a disparam."""

    model_config = ConfigDict(frozen=True)

    id: CategoriaFator
    peso: int = Field(gt=0)
    descricao: ModeloDescricao
    padroes: tuple[PadraoNormalizado, ...] = Field(min_length=1)


class Regras(BaseModel):
    """O `regras.yaml` inteiro, validado."""

    model_config = ConfigDict(frozen=True)

    versao: int = Field(ge=1, description="Muda a cada recalibração; carimbada no relatório.")
    agregacao: Literal["por_categoria"]
    faixas: Faixas
    urls: ConfiguracaoURLs
    categorias: tuple[CategoriaTexto, ...]

    @model_validator(mode="after")
    def _seis_categorias_sem_repetir(self) -> Self:
        presentes = [categoria.id for categoria in self.categorias]
        faltando = sorted(set(CATEGORIAS_DE_TEXTO) - set(presentes))
        if faltando:
            raise ValueError(f"categorias da §5.4.1 ausentes no regras.yaml: {faltando}")
        if len(presentes) != len(set(presentes)):
            raise ValueError(f"categoria repetida no regras.yaml: {presentes}")
        return self


@lru_cache
def carregar_regras() -> Regras:
    """Lê e valida o `regras.yaml`. Chamado em `criar_app()` para que o erro apareça no boot."""
    with CAMINHO_REGRAS.open(encoding="utf-8") as arquivo:
        # `safe_load`, nunca `load`: o YAML é nosso, mas `load` constrói objetos Python
        # arbitrários e não há motivo para deixar essa porta aberta.
        return Regras.model_validate(yaml.safe_load(arquivo))
