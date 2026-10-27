"""O contrato da resposta da IA: o schema enviado à API e a validação da volta (ADR-0020).

A saída estruturada da Anthropic (`output_config.format`, tipo `json_schema`) garante a forma:
campos, tipos e o enum do nível. Ela não aceita `maxItems`, `maxLength` nem `minItems` acima de
1 (documentação de *Structured outputs*), então a contagem de sinais e de passos é conferida
aqui, pelo Pydantic. Inválida é plano B.

A ordem dos campos é de propósito: o modelo escreve o tipo e os sinais antes de escolher o
nível, e o nível sai do que ele acabou de escrever.

Sem campo de confiança: a porcentagem que vale é a medida no corpus, não a que o modelo declara.
"""

from typing import Any, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.formulator.limpeza import afirma_seguranca, limpar_texto
from app.schemas.analise import (
    ITEM_MAX_CARACTERES,
    PASSOS_MAX,
    PASSOS_MIN,
    SINAIS_MAX,
    TIPO_MAX_CARACTERES,
    ExplicacaoIA,
    NivelRisco,
)

SCHEMA_SAIDA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["tipo", "sinais", "nivel_sugerido", "o_que_fazer"],
    "properties": {
        "tipo": {
            "type": "string",
            "description": "O que a mensagem parece ser, em até 8 palavras.",
        },
        "sinais": {
            "type": "array",
            "items": {"type": "string"},
            "description": f"De 0 a {SINAIS_MAX} frases curtas sobre esta mensagem.",
        },
        "nivel_sugerido": {"type": "string", "enum": list(get_args(NivelRisco))},
        "o_que_fazer": {
            "type": "array",
            "items": {"type": "string"},
            "description": f"De {PASSOS_MIN} a {PASSOS_MAX} passos concretos para esta mensagem.",
        },
    },
}


class SaidaIA(BaseModel):
    """A resposta da IA como veio, validada, mas ainda não limpa."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tipo: str
    sinais: tuple[str, ...] = Field(max_length=SINAIS_MAX)
    nivel_sugerido: NivelRisco
    o_que_fazer: tuple[str, ...] = Field(min_length=PASSOS_MIN, max_length=PASSOS_MAX)

    @field_validator("nivel_sugerido", mode="before")
    @classmethod
    def _caixa_alta(cls, valor: object) -> object:
        # A documentação avisa que o modelo pode mudar a caixa de um valor do enum.
        return valor.strip().upper() if isinstance(valor, str) else valor


class SaidaInutilizavel(Exception):
    """A explicação não cumpre o mínimo depois da limpeza: a tela usa o plano B do nível final.

    Só a explicação é descartada. O nível sugerido já passou na validação de forma e continua
    valendo na combinação (ADR-0020): nenhuma validação de texto reduz o nível.
    """


def explicacao_da_saida(saida: SaidaIA) -> ExplicacaoIA:
    """Limpa cada campo e confere o que sobrou. É o único caminho da IA até a tela.

    O item que afirma segurança sai sozinho, e os outros ficam. Descartar a saída inteira por
    causa de uma frase jogava fora o nível ALTO junto (defeito da bateria da fatia 6).
    """
    tipo = limpar_texto(saida.tipo, limite=TIPO_MAX_CARACTERES)
    if afirma_seguranca(tipo):
        tipo = ""
    sinais = _limpar_itens(saida.sinais)
    passos = _limpar_itens(saida.o_que_fazer)
    if not tipo:
        raise SaidaInutilizavel("o tipo ficou vazio depois da limpeza")
    if len(passos) < PASSOS_MIN:
        raise SaidaInutilizavel("sobraram menos passos que o mínimo depois da limpeza")
    return ExplicacaoIA(tipo=tipo, sinais=sinais, o_que_fazer=passos)


def _limpar_itens(itens: tuple[str, ...]) -> tuple[str, ...]:
    limpos = (limpar_texto(item, limite=ITEM_MAX_CARACTERES) for item in itens)
    return tuple(item for item in limpos if item and not afirma_seguranca(item))
