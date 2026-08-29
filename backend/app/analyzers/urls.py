"""URLExtractor — encontra os links do texto e os reduz a uma forma canônica (§5.4.2 do RFC).

É um *extrator*, não um analisador: devolve `list[URLExtraida]`, não `list[Fator]`. Nenhum peso
do RFC pertence à extração — typosquatting, TLD de alto risco, idade do domínio e reputação são
do DomainAnalyzer (Fase 3) e do URLChecker (Fase 4), que recebem exatamente esta lista.

A forma canônica é decidida no ADR-0009. Ela é a entrada da Fase 3 e, hasheada, a chave do
cache da Fase 4 — por isso precisa ser estável e não pode depender de como o usuário digitou.
"""

import re
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel

from app.scoring.regras import ConfiguracaoURLs

PORTA_PADRAO = {"http": 80, "https": 443}

# Pontuação que encosta no fim de um link dentro de uma frase e não faz parte dele.
_PONTUACAO_FINAL = ".,;:!?)]}>\"'«»"


class URLExtraida(BaseModel):
    """Um link encontrado no texto, na forma que o usuário digitou e na forma canônica."""

    original: str
    canonica: str
    host: str


class URLExtractor:
    """Extrai as quatro formas da §5.4.2: completa, sem protocolo, encurtada e embutida."""

    def __init__(self, config: ConfiguracaoURLs) -> None:
        self._maximo = config.maximo_por_analise
        self._padrao = _montar_padrao(config.tlds_conhecidos)

    def extrair(self, texto: str) -> list[URLExtraida]:
        """Devolve os links na ordem de aparição, sem repetir a mesma forma canônica."""
        encontradas: dict[str, URLExtraida] = {}
        for casamento in self._padrao.finditer(texto):
            bruta = casamento.group().rstrip(_PONTUACAO_FINAL)
            url = _canonicalizar(bruta)
            if url is not None and url.canonica not in encontradas:
                encontradas[url.canonica] = url
            if len(encontradas) == self._maximo:
                break
        return list(encontradas.values())


def _montar_padrao(tlds: frozenset[str]) -> re.Pattern[str]:
    """Uma alternância só, para que as formas sejam tentadas na ordem e não se sobreponham."""
    rotulo = r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
    # A lista de TLDs vale apenas para host sem protocolo: sem ela, "relatorio.final" e
    # "Obrigado.Att" viram link. Com `http://` explícito não há ambiguidade e ela não se aplica.
    conhecidos = "|".join(sorted(map(re.escape, tlds), key=len, reverse=True))
    return re.compile(
        # Não começar no meio de uma palavra, de um domínio ou depois de um "@": é o que
        # impede que `contato@banco.com.br` seja lido como o link `banco.com.br`.
        r"(?<![\w@.-])"
        r"(?:"
        rf"https?://\S+"  # completa
        rf"|www\.{rotulo}(?:\.{rotulo})+(?:/\S*)?"  # sem protocolo
        rf"|{rotulo}(?:\.{rotulo})*\.(?:{conhecidos})\b(?:[/?]\S*)?"  # encurtada / embutida
        r")",
        re.IGNORECASE,
    )


def _canonicalizar(bruta: str) -> URLExtraida | None:
    """Host minúsculo e sem ponto final, sem usuário, sem fragmento, sem porta padrão.

    Devolve `None` para o que casou o padrão mas não é URL utilizável (host vazio, porta
    inválida) — melhor descartar em silêncio que carregar lixo para as fases seguintes.
    """
    com_esquema = bruta if "://" in bruta else f"http://{bruta}"
    try:
        partes = urlsplit(com_esquema)
        porta = partes.port
    except ValueError:
        return None

    # `hostname` já vem minúsculo e sem o `usuario@` — que é justamente o que precisamos
    # descartar: em `http://bradesco.com.br@golpe.xyz` o host real é golpe.xyz.
    host = (partes.hostname or "").rstrip(".")
    if not host:
        return None

    esquema = partes.scheme.lower()
    autoridade = host if porta in (None, PORTA_PADRAO.get(esquema)) else f"{host}:{porta}"
    caminho = partes.path or "/"
    return URLExtraida(
        original=bruta,
        canonica=urlunsplit((esquema, autoridade, caminho, partes.query, "")),
        host=host,
    )
