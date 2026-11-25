"""Google Safe Browsing, Lookup API v4 (`threatMatches.find`). ADR-0028.

Só consulta: pergunta se um endereço está na lista do Google. O que sai daqui é `http://<host>/`
e `https://<host>/` — nunca o caminho, a query nem o fragmento do link da mensagem.

A chave vai na query (`?key=`), a única forma que a documentação descreve. Por isso nenhuma
exceção daqui carrega a URL chamada: toda falha vira `FonteIndisponivel`, com `from None`.
"""

from urllib.parse import urlsplit

import httpx

from app.reputation.tipos import FonteIndisponivel, para_consulta

ENDERECO = "https://safebrowsing.googleapis.com/v4/threatMatches:find"

# Os quatro tipos de ameaça da lista. "Qualquer plataforma": a pessoa pode abrir o link em
# qualquer aparelho.
_TIPOS_DE_AMEACA = [
    "MALWARE",
    "SOCIAL_ENGINEERING",
    "UNWANTED_SOFTWARE",
    "POTENTIALLY_HARMFUL_APPLICATION",
]


class ClienteSafeBrowsing:
    def __init__(self, http: httpx.AsyncClient, chave: str, timeout_s: float) -> None:
        self._http = http
        self._chave = chave
        self._timeout_s = timeout_s

    async def consultar(self, hosts: list[str]) -> dict[str, float]:
        """Os hosts que o Google apontou, cada um com os segundos pelos quais a resposta vale
        (`cacheDuration`). Host que não aparece não foi apontado. Uma chamada para todos."""
        # Na consulta o host vai em ASCII; na volta, o nome é o que recebemos.
        original = {para_consulta(host): host for host in hosts}
        corpo = {
            "client": {"clientId": "verifyscan", "clientVersion": "1"},
            "threatInfo": {
                "threatTypes": _TIPOS_DE_AMEACA,
                "platformTypes": ["ANY_PLATFORM"],
                "threatEntryTypes": ["URL"],
                "threatEntries": [
                    {"url": f"{esquema}://{host}/"}
                    for host in original
                    for esquema in ("http", "https")
                ],
            },
        }
        try:
            resposta = await self._http.post(
                ENDERECO, params={"key": self._chave}, json=corpo, timeout=self._timeout_s
            )
        except httpx.TimeoutException:
            raise FonteIndisponivel("timeout") from None
        except httpx.HTTPError:
            raise FonteIndisponivel("erro") from None
        if resposta.status_code == 429:
            raise FonteIndisponivel("limite")
        if resposta.status_code != 200:
            raise FonteIndisponivel("http")
        try:
            apontados = _apontados(resposta.json(), set(original))
            return {original[host]: validade for host, validade in apontados.items()}
        except (ValueError, TypeError, KeyError, AttributeError):
            raise FonteIndisponivel("resposta") from None


def _apontados(dados: object, consultados: set[str]) -> dict[str, float]:
    """Sem correspondência, o Google devolve `{}`. Com, uma lista em `matches`."""
    if not isinstance(dados, dict):
        raise TypeError("resposta que não é objeto")
    apontados: dict[str, float] = {}
    for item in dados.get("matches", []):
        host = urlsplit(item["threat"]["url"]).hostname or ""
        if host not in consultados:
            continue
        validade = float(str(item["cacheDuration"]).removesuffix("s"))
        # Dois avisos do mesmo host: vale o que vence antes, para nunca usar dado velho.
        apontados[host] = min(validade, apontados.get(host, validade))
    return apontados
