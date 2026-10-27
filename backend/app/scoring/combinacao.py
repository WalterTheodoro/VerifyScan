"""A regra fixa que junta o nível do motor e o sugerido pela IA (ADR-0020).

Mora em `scoring/`, e não no pacote da IA, de propósito: quem decide o nível final é o sistema,
não o modelo. A IA só sugere.
"""

from app.schemas.analise import NivelRisco

_ORDEM: dict[NivelRisco, int] = {"BAIXO": 0, "MEDIO": 1, "ALTO": 2}


def combinar(nivel_motor: NivelRisco, nivel_ia: NivelRisco | None) -> NivelRisco:
    """O maior dos dois. A IA pode subir o nível, nunca baixar (OWASP LLM01): uma mensagem que
    convença o modelo de que é segura não apaga o que o motor já encontrou."""
    if nivel_ia is None:
        return nivel_motor
    return max(nivel_motor, nivel_ia, key=_ORDEM.__getitem__)
