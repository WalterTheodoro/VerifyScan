"""O Azure visto de dentro da VM, com a identidade da própria VM (ADR-0029).

Não existe senha, chave nem arquivo de credencial: a VM pede um token ao serviço de metadados
dela (um endereço que só responde de dentro da VM) e o apresenta ao cofre. O que ela pode fazer
com esse token é o que os papéis do `infra/main.bicep` dizem, e nada mais.

A rede entra por parâmetro (`pedir`): nos testes, um transporte falso (CLAUDE.md §6).
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

# (método, URL, cabeçalhos, corpo) → (status, corpo da resposta).
Pedir = Callable[[str, str, dict[str, str], bytes | None], tuple[int, bytes]]

_METADADOS = "http://169.254.169.254/metadata/identity/oauth2/token"
_COFRES = "https://vault.azure.net"
_TETO_S = 30


class ErroDoAzure(Exception):
    """O Azure recusou ou não respondeu. A mensagem leva só o status: nunca o corpo da resposta
    nem o valor de um segredo."""


def pedir_http(
    metodo: str, url: str, cabecalhos: dict[str, str], corpo: bytes | None
) -> tuple[int, bytes]:
    """A rede de verdade. Um status de erro volta como status, e não como exceção: quem chamou
    decide o que 404 quer dizer."""
    pedido = urllib.request.Request(url, data=corpo, headers=cabecalhos, method=metodo)
    try:
        with urllib.request.urlopen(pedido, timeout=_TETO_S) as resposta:
            return int(resposta.status), resposta.read()
    except urllib.error.HTTPError as erro:
        return erro.code, erro.read()


class Azure:
    def __init__(self, pedir: Pedir = pedir_http) -> None:
        self._pedir = pedir
        self._tokens: dict[str, str] = {}

    def _token(self, servico: str) -> str:
        """O token da identidade da VM para um serviço. Pedido uma vez por serviço e guardado só
        em memória, enquanto o processo vive."""
        if servico not in self._tokens:
            consulta = urllib.parse.urlencode({"api-version": "2018-02-01", "resource": servico})
            status, corpo = self._pedir(
                "GET", f"{_METADADOS}?{consulta}", {"Metadata": "true"}, None
            )
            if status != 200:
                raise ErroDoAzure(f"A VM não conseguiu o token da identidade dela ({status}).")
            self._tokens[servico] = str(json.loads(corpo)["access_token"])
        return self._tokens[servico]

    def ler_segredo(self, cofre: str, nome: str) -> str | None:
        """O valor do segredo, ou `None` se o nome não existe no cofre."""
        status, corpo = self._pedir(
            "GET",
            f"https://{cofre}.vault.azure.net/secrets/{nome}?api-version=7.4",
            {"Authorization": f"Bearer {self._token(_COFRES)}"},
            None,
        )
        if status == 404:
            return None
        if status != 200:
            raise ErroDoAzure(f"O cofre respondeu {status} ao ler {nome}.")
        return str(json.loads(corpo)["value"])
