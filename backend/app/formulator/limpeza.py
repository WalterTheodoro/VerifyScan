"""Limpeza do texto que a IA escreveu, antes de ele chegar à tela ou ao banco (ADR-0020).

A IA leu a mensagem do golpista e pode repetir dela o link, o telefone ou o e-mail. Mostrar isso
seria entregar à pessoa o atalho para o golpe. Aqui eles saem, junto com HTML e caracteres de
controle, e cada campo é cortado no teto. O React já escapa o texto; tirar o HTML é para que a
tela nunca mostre uma tag como se fosse conteúdo.

Os padrões de telefone e e-mail têm a mesma forma dos de `tools/pii.py`, mas não são importados
de lá: `tools/` protege o repositório e não faz parte da aplicação. Os links reaproveitam o
`URLExtractor`, o mesmo que acha os links da mensagem. Os padrões de e-mail, esquema e telefone são
públicos porque a transcrição do print na tela troca as mesmas coisas (`ServicoAnalise.para_exibir`,
correção 9.1).
"""

import re
import unicodedata
from functools import lru_cache

from app.analyzers.normalizacao import normalizar
from app.analyzers.urls import URLExtractor
from app.scoring.regras import carregar_regras

LINK_REMOVIDO = "[link removido]"
EMAIL_REMOVIDO = "[e-mail removido]"
TELEFONE_REMOVIDO = "[telefone removido]"

PADRAO_EMAIL = re.compile(r"(?<![\w.+-])[\w.+%-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+(?![\w-])")

# Qualquer esquema (`ftp://`, `intent://`): o `URLExtractor` só procura http e https.
PADRAO_ESQUEMA = re.compile(r"[a-z][a-z0-9+.-]*://\S+", re.IGNORECASE)

PADRAO_TELEFONE = re.compile(
    r"""
    (?<![\d@.,-])                  # não começar no meio de um número ou de um e-mail
    (?:
        0800[\s.-]?\d{3}[\s.-]?\d{4}   # 0800
      | (?:\+?55[\s.-]?)?              # código do país, opcional
        (?:\(\d{2}\)\s?|\d{2}[\s.-]?)? # DDD, com ou sem parênteses
        \d{4,5}[\s.-]?\d{4}            # celular (9 dígitos) ou fixo (8)
    )
    (?![\d@-])
    """,
    re.VERBOSE,
)

_TAG = re.compile(r"<[^>]*>")
_ESPACOS = re.compile(r"\s+")

# Teto de voltas: cada volta troca os links por um marcador que não é link, então duas bastam.
# O `URLExtractor` não repete a mesma forma canônica — `golpe.com` e `GOLPE.com` saem em voltas
# diferentes.
_VOLTAS_MAXIMAS = 5


@lru_cache
def _extrator() -> URLExtractor:
    return URLExtractor(carregar_regras().urls)


def limpar_texto(texto: str, limite: int | None = None) -> str:
    """Tira e-mail, link, telefone, HTML e caracteres de controle; corta em `limite`."""
    limpo = PADRAO_EMAIL.sub(EMAIL_REMOVIDO, texto)
    limpo = PADRAO_ESQUEMA.sub(LINK_REMOVIDO, limpo)
    for _ in range(_VOLTAS_MAXIMAS):
        urls = _extrator().extrair(limpo)
        if not urls:
            break
        for url in urls:
            limpo = limpo.replace(url.original, LINK_REMOVIDO)
    limpo = PADRAO_TELEFONE.sub(TELEFONE_REMOVIDO, limpo)
    limpo = _TAG.sub(" ", limpo).replace("<", " ").replace(">", " ")
    limpo = "".join(" " if unicodedata.category(c) == "Cc" else c for c in limpo)
    limpo = _ESPACOS.sub(" ", limpo).strip()
    if limite is not None and len(limpo) > limite:
        limpo = _cortar(limpo, limite)
    return limpo


def _cortar(texto: str, limite: int) -> str:
    """Corta na última palavra inteira que cabe, com reticências."""
    cabe = texto[: limite - 1]
    if " " in cabe:
        cabe = cabe.rsplit(" ", 1)[0]
    return cabe.rstrip(" ,;:.-") + "…"


# ─── afirmação positiva de segurança ──────────────────────────────────────────────────────

# "não é golpe" já carrega a negação: é a própria afirmação que o sistema nunca faz.
_NAO_E_GOLPE = re.compile(r"\bnao e (?:um )?golpe\b")
# As outras só contam sem um "não", "nunca", "nem" ou "jamais" imediatamente antes: "a mensagem
# não é segura" e "nunca é seguro passar o código" são avisos certos para golpe.
_AFIRMACAO = re.compile(
    r"\b(?:e|esta) (?:segur[ao]|confiavel|verdadeir[ao]|legitim[ao])\b|\bpode confiar\b"
)
_NEGACOES = frozenset({"nao", "nunca", "nem", "jamais"})
# Fala relatada não é afirmação: "a mensagem diz que é segura" descreve o golpe, e é o que a IA
# escreve quando cita a injeção como sinal. Conta se um destes verbos vier até `_JANELA_RELATO`
# palavras antes, na mesma oração.
_RELATO = frozenset(
    {
        "diz", "dizem", "disse", "dizer", "dizendo",
        "afirma", "afirmam", "afirmar", "afirmando",
        "alega", "alegam", "alegar", "alegando",
        "promete", "prometem", "prometer", "prometendo",
        "garante", "garantem", "garantir", "garantindo",
        "jura", "juram", "jurando",
        "confirmar", "confirmando", "confirme", "confirma",
        "informar", "informada", "informado",
    }
)  # fmt: skip
_JANELA_RELATO = 6
# Condição não é afirmação: "confira se o boleto é verdadeiro" é conselho. Janela curta — o "se"
# precisa estar colado no sujeito — para que "se for do banco ela é segura" continue contando.
_JANELA_CONDICAO = 4
# Aspas simples curvas e travessão curto vão em escape (U+2018, U+2019, U+2013): à vista, o
# ruff os confunde com acento grave e hífen.
_ORACAO = re.compile(r"[.,;:!?()\[\]{}\"“”\u2018\u2019«»—\u2013…]")
_PONTUACAO = re.compile(r"[^\w\s]")


def afirma_seguranca(texto: str) -> bool:
    """`True` quando o texto afirma que a mensagem é segura — o que o sistema nunca diz.

    Comparado sem acento e sem pontuação: "Não é golpe." e "nao e golpe" são a mesma frase. A
    pontuação separa as orações antes: o relato e a condição só valem dentro da oração deles.
    """
    for oracao in _ORACAO.split(normalizar(texto)):
        frase = _ESPACOS.sub(" ", _PONTUACAO.sub(" ", oracao)).strip()
        if _afirma_na_oracao(frase):
            return True
    return False


def _afirma_na_oracao(frase: str) -> bool:
    for casamento in _NAO_E_GOLPE.finditer(frase):
        if not _relatada_ou_condicional(frase[: casamento.start()].split()):
            return True
    for casamento in _AFIRMACAO.finditer(frase):
        anteriores = frase[: casamento.start()].split()
        if anteriores and anteriores[-1] in _NEGACOES:
            continue
        if not _relatada_ou_condicional(anteriores):
            return True
    return False


# ─── fala do sistema por dentro (pendência da fatia 7) ────────────────────────────────────

# "O motor marcou pressa…": quem lê não sabe o que é o motor, e a frase faz a análise parecer
# um sistema falando de si. O prompt proíbe estas palavras; isto é a segunda barreira. Os quatro
# últimos termos o prompt proíbe desde a fatia 6, e a varredura da calibração da fatia 8 ainda os
# achou na tela ("instruções internas", "sistema de análise").
_FALA_DO_SISTEMA = re.compile(
    r"\b(?:motor|algoritmo|fator(?:es)?|pistas?|prompt|injecao|instrucoes internas"
    r"|sistemas? de analise)\b"
)


def fala_do_sistema(texto: str) -> bool:
    """`True` quando o texto fala do motor, do algoritmo, dos fatores, das pistas ou usa o jargão
    de injeção ("prompt", "injeção", "instruções internas", "sistema de análise").

    Palavra inteira, sem acento e sem caixa: "Os FATORES" conta, "fatorar" não."""
    return _FALA_DO_SISTEMA.search(normalizar(texto)) is not None


def _relatada_ou_condicional(anteriores: list[str]) -> bool:
    relato = not _RELATO.isdisjoint(anteriores[-_JANELA_RELATO:])
    return relato or "se" in anteriores[-_JANELA_CONDICAO:]
