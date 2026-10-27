"""Limpeza do texto que a IA escreveu, antes de ele chegar à tela ou ao banco (ADR-0020).

A IA leu a mensagem do golpista e pode repetir dela o link, o telefone ou o e-mail. Mostrar isso
seria entregar à pessoa o atalho para o golpe. Aqui eles saem, junto com HTML e caracteres de
controle, e cada campo é cortado no teto. O React já escapa o texto; tirar o HTML é para que a
tela nunca mostre uma tag como se fosse conteúdo.

Os padrões de telefone e e-mail têm a mesma forma dos de `tools/pii.py`, mas não são importados
de lá: `tools/` protege o repositório e não faz parte da aplicação. Os links reaproveitam o
`URLExtractor`, o mesmo que acha os links da mensagem.
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

_EMAIL = re.compile(r"(?<![\w.+-])[\w.+%-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+(?![\w-])")

# Qualquer esquema (`ftp://`, `intent://`): o `URLExtractor` só procura http e https.
_ESQUEMA = re.compile(r"[a-z][a-z0-9+.-]*://\S+", re.IGNORECASE)

_TELEFONE = re.compile(
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
    limpo = _EMAIL.sub(EMAIL_REMOVIDO, texto)
    limpo = _ESQUEMA.sub(LINK_REMOVIDO, limpo)
    for _ in range(_VOLTAS_MAXIMAS):
        urls = _extrator().extrair(limpo)
        if not urls:
            break
        for url in urls:
            limpo = limpo.replace(url.original, LINK_REMOVIDO)
    limpo = _TELEFONE.sub(TELEFONE_REMOVIDO, limpo)
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
_PONTUACAO = re.compile(r"[^\w\s]")


def afirma_seguranca(texto: str) -> bool:
    """`True` quando o texto afirma que a mensagem é segura — o que o sistema nunca diz.

    Comparado sem acento e sem pontuação: "Não é golpe." e "nao e golpe" são a mesma frase.
    """
    frase = _ESPACOS.sub(" ", _PONTUACAO.sub(" ", normalizar(texto))).strip()
    if _NAO_E_GOLPE.search(frase):
        return True
    for casamento in _AFIRMACAO.finditer(frase):
        anteriores = frase[: casamento.start()].split()
        if not anteriores or anteriores[-1] not in _NEGACOES:
            return True
    return False
