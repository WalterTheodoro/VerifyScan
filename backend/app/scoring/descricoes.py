"""Templates de descrição de fator (ADR-0004).

A descrição que chega ao usuário — e, na Fase 7, à LLM — nunca é texto livre gerado no código
nem trecho do conteúdo enviado. É um template versionado no `regras.yaml`, preenchido apenas
por valores de um conjunto fechado e tipado. Isso é a invariante 1 do CLAUDE.md expressa no
tipo, e não numa convenção que alguém precise lembrar.

A Fase 1 só usa templates sem placeholder. O mecanismo existe desde já porque a Fase 3 precisa
de `{dominio}` e `{marca}`, e porque o teste da invariante só significa alguma coisa se houver
como conferir uma descrição contra o template que a produziu (`corresponde`).
"""

import re
from typing import TypedDict

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class ValoresDescricao(TypedDict, total=False):
    """Tudo que pode preencher um placeholder. Nada aqui vem do texto do usuário.

    `dominio` e `marca` são valores derivados e normalizados (host da URL, nome da marca da
    lista versionada), não recortes da mensagem.
    """

    dominio: str
    marca: str
    engines: int
    idade_dias: int


# Uma fonte de verdade só: o conjunto permitido é literalmente o TypedDict acima.
PLACEHOLDERS_PERMITIDOS: frozenset[str] = frozenset(ValoresDescricao.__annotations__)

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


class ModeloDescricao(BaseModel):
    """Um template de descrição, validado no carregamento do `regras.yaml`."""

    model_config = ConfigDict(frozen=True)

    template: str

    @model_validator(mode="before")
    @classmethod
    def _aceitar_string_solta(cls, valor: object) -> object:
        """No YAML a descrição é uma string; aqui ela vira o modelo que carrega o mecanismo."""
        return {"template": valor} if isinstance(valor, str) else valor

    @field_validator("template")
    @classmethod
    def _validar_placeholders(cls, template: str) -> str:
        ocorrencias = _PLACEHOLDER.findall(template)
        desconhecidos = sorted(set(ocorrencias) - PLACEHOLDERS_PERMITIDOS)
        if desconhecidos:
            raise ValueError(
                f"placeholder fora do conjunto permitido: {desconhecidos}. "
                f"Permitidos: {sorted(PLACEHOLDERS_PERMITIDOS)}"
            )
        # Chave solta ou placeholder mal formado (`{ }`, `{texto do usuario}`) passaria pela
        # checagem acima e só estouraria na renderização, em produção.
        if template.count("{") != len(ocorrencias) or template.count("}") != len(ocorrencias):
            raise ValueError(f"chaves desbalanceadas ou placeholder mal formado: {template!r}")
        return template

    @property
    def placeholders(self) -> frozenset[str]:
        return frozenset(_PLACEHOLDER.findall(self.template))

    def renderizar(self, valores: ValoresDescricao | None = None) -> str:
        """Preenche o template. Placeholder declarado e não fornecido levanta `KeyError`."""
        return self.template.format_map(valores or {})

    def corresponde(self, descricao: str) -> bool:
        """A descrição poderia ter saído deste template?

        Usado pelo teste da invariante 1: toda descrição produzida pelo motor precisa
        corresponder a algum template do `regras.yaml`.
        """
        # `split` com grupo de captura devolve [literal, placeholder, literal, ...]:
        # os índices ímpares são os nomes capturados, e viram `.+`.
        partes = _PLACEHOLDER.split(self.template)
        padrao = "".join(
            ".+" if indice % 2 else re.escape(parte) for indice, parte in enumerate(partes)
        )
        return re.fullmatch(padrao, descricao) is not None
