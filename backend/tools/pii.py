"""Detectores de dados pessoais em texto — insumo do guard de PII do CI.

O `corpus/casos/` é público e versionado: um caso real colado sem anonimizar vira PII no
histórico do Git, onde `git rm` não desfaz. Estes detectores são a parte que *encontra*; o
scanner que varre o corpus e o workflow que barra o commit vêm depois, em PRs separados.

Duas escolhas que valem registro:

1. **Aqui não se decide risco.** Este módulo mora em `tools/` e não em `app/analyzers/`: ele
   protege o repositório, não pontua mensagem. Nada daqui alimenta o ScoringEngine.
2. **O erro tem lado preferido.** Num guard de CI, o custo de um falso positivo é uma revisão
   humana; o de um falso negativo é dado pessoal publicado. Por isso os padrões de telefone e
   valor são largos de propósito — uma sequência de 11 dígitos é reportada como telefone mesmo
   quando é outra coisa. O CPF é a exceção: ele tem dígito verificador, então dá para exigir
   prova, e exigir sai mais barato do que reportar todo número de 11 dígitos como CPF.
"""

import re
from dataclasses import dataclass

CPF = "cpf"
TELEFONE = "telefone"
EMAIL = "email"
VALOR_MONETARIO = "valor_monetario"


@dataclass(frozen=True)
class Achado:
    """Um trecho suspeito de ser dado pessoal, com onde ele está no texto."""

    tipo: str
    valor: str
    inicio: int
    fim: int


# ─── CPF ──────────────────────────────────────────────────────────────────────────────────

# As duas formas em que um CPF é escrito. A pontuada vem primeiro para vencer a alternância
# quando as duas casariam; os lookarounds impedem casar 11 dígitos no meio de um número maior.
_CPF = re.compile(r"(?<!\d)(?:\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})(?!\d)")


def detectar_cpf(texto: str) -> list[Achado]:
    """Encontra CPFs válidos. O que não passa no dígito verificador não vira achado."""
    return [
        Achado(CPF, casamento.group(), casamento.start(), casamento.end())
        for casamento in _CPF.finditer(texto)
        if _cpf_valido(re.sub(r"\D", "", casamento.group()))
    ]


def _cpf_valido(digitos: str) -> bool:
    """Confere os dois dígitos verificadores (módulo 11) dos 11 dígitos já sem pontuação."""
    # 111.111.111-11 e os outros dez repetidos passam no módulo 11 por acidente aritmético.
    if len(set(digitos)) == 1:
        return False
    numeros = [int(digito) for digito in digitos]
    for tamanho in (9, 10):
        soma = sum(numero * (tamanho + 1 - i) for i, numero in enumerate(numeros[:tamanho]))
        if numeros[tamanho] != (soma * 10 % 11) % 10:
            return False
    return True


# ─── telefone ─────────────────────────────────────────────────────────────────────────────

_TELEFONE = re.compile(
    r"""
    (?<![\d@.,-])                  # não começar no meio de um número ou de um e-mail
    (?:\+?55[\s.-]?)?              # código do país, opcional
    (?:\(\d{2}\)\s?|\d{2}[\s.-]?)? # DDD, com ou sem parênteses, com ou sem separador
    \d{4,5}[\s.-]?\d{4}            # celular (9 dígitos) ou fixo (8), com ou sem hífen
    (?![\d@-])
    """,
    re.VERBOSE,
)


def detectar_telefone(texto: str) -> list[Achado]:
    """Encontra celulares e fixos brasileiros nas formas em que as pessoas os escrevem."""
    return [
        Achado(TELEFONE, casamento.group(), casamento.start(), casamento.end())
        for casamento in _TELEFONE.finditer(texto)
    ]


# ─── e-mail ───────────────────────────────────────────────────────────────────────────────

# Deliberadamente mais permissivo que a RFC 5322: aqui basta ter cara de e-mail para merecer
# revisão. O ponto final da frase fica de fora porque o lookahead não recusa "." depois do TLD.
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+%-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+(?![\w-])")


def detectar_email(texto: str) -> list[Achado]:
    """Encontra endereços de e-mail."""
    return [
        Achado(EMAIL, casamento.group(), casamento.start(), casamento.end())
        for casamento in _EMAIL.finditer(texto)
    ]


# ─── valor monetário ──────────────────────────────────────────────────────────────────────

# Separadores brasileiros: ponto agrupa milhar, vírgula separa centavo. A forma agrupada vem
# primeiro para que "1.234,56" não case só como "1".
_NUMERO = r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?"
_VALOR = re.compile(rf"R\$\s*(?:{_NUMERO})|(?:{_NUMERO})\s*reais?", re.IGNORECASE)


def detectar_valor_monetario(texto: str) -> list[Achado]:
    """Encontra quantias em reais, prefixadas por "R$" ou seguidas da palavra "reais"."""
    return [
        Achado(VALOR_MONETARIO, casamento.group(), casamento.start(), casamento.end())
        for casamento in _VALOR.finditer(texto)
    ]


# ─── varredura ────────────────────────────────────────────────────────────────────────────


def varrer(texto: str) -> list[Achado]:
    """Roda os quatro detectores e devolve os achados na ordem em que aparecem no texto.

    Os detectores são independentes e podem se sobrepor: 11 dígitos seguidos que passem no
    dígito verificador saem como CPF *e* como telefone. Para o guard isso não é problema —
    ele só precisa saber que há algo ali.
    """
    achados = (
        detectar_cpf(texto)
        + detectar_telefone(texto)
        + detectar_email(texto)
        + detectar_valor_monetario(texto)
    )
    return sorted(achados, key=lambda achado: (achado.inicio, achado.tipo))
