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
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from email.utils import formatdate, parsedate_to_datetime

# (método, URL, cabeçalhos, corpo) → (status, corpo da resposta).
Pedir = Callable[[str, str, dict[str, str], bytes | None], tuple[int, bytes]]

_METADADOS = "http://169.254.169.254/metadata/identity/oauth2/token"
_COFRES = "https://vault.azure.net"
_ARMAZENAMENTO = "https://storage.azure.com/"
# A versão da API de blobs. Com token (e não chave de conta), o cabeçalho é obrigatório.
_VERSAO_DOS_BLOBS = "2023-11-03"
_TETO_S = 30


@dataclass(frozen=True)
class Blob:
    nome: str
    modificado: datetime


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

    # ─── blobs (o backup) ─────────────────────────────────────────────────────────────────

    def _blob(
        self, metodo: str, conta: str, caminho: str, corpo: bytes | None, esperado: int
    ) -> bytes:
        cabecalhos = {
            "Authorization": f"Bearer {self._token(_ARMAZENAMENTO)}",
            "x-ms-version": _VERSAO_DOS_BLOBS,
            "x-ms-date": formatdate(usegmt=True),
        }
        if corpo is not None:
            cabecalhos["x-ms-blob-type"] = "BlockBlob"
            cabecalhos["Content-Type"] = "application/octet-stream"
        url = f"https://{conta}.blob.core.windows.net/{caminho}"
        status, resposta = self._pedir(metodo, url, cabecalhos, corpo)
        if status != esperado:
            raise ErroDoAzure(f"O armazenamento respondeu {status} ({metodo}).")
        return resposta

    def enviar_blob(self, conta: str, container: str, nome: str, conteudo: bytes) -> None:
        self._blob("PUT", conta, f"{container}/{urllib.parse.quote(nome)}", conteudo, 201)

    def baixar_blob(self, conta: str, container: str, nome: str) -> bytes:
        return self._blob("GET", conta, f"{container}/{urllib.parse.quote(nome)}", None, 200)

    def apagar_blob(self, conta: str, container: str, nome: str) -> None:
        self._blob("DELETE", conta, f"{container}/{urllib.parse.quote(nome)}", None, 202)

    def listar_blobs(self, conta: str, container: str) -> list[Blob]:
        """Os blobs do container, com a data em que cada um foi gravado. Uma página só (até
        5000 nomes): o container guarda uma semana de backups."""
        resposta = self._blob("GET", conta, f"{container}?restype=container&comp=list", None, 200)
        # A resposta é XML: <Blob><Name>…</Name><Properties><Last-Modified>…</…></…></Blob>.
        blobs = []
        for item in ET.fromstring(resposta).iter("Blob"):
            nome = item.findtext("Name")
            modificado = item.findtext("Properties/Last-Modified")
            if nome and modificado:
                blobs.append(Blob(nome, parsedate_to_datetime(modificado)))
        return blobs
