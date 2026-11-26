"""As chamadas ao Azure com a identidade da VM, contra um transporte falso."""

import json

import pytest

from vm.azure import Azure, ErroDoAzure

IMDS = "http://169.254.169.254/metadata/identity/oauth2/token"
MARCA = "MARCA-DE-SEGREDO"


class Transporte:
    """No lugar da rede: responde pelo começo da URL e anota os pedidos."""

    def __init__(self, respostas: dict[str, tuple[int, bytes]]) -> None:
        self.respostas = respostas
        self.pedidos: list[tuple[str, str, dict[str, str]]] = []

    def __call__(
        self, metodo: str, url: str, cabecalhos: dict[str, str], corpo: bytes | None
    ) -> tuple[int, bytes]:
        self.pedidos.append((metodo, url, cabecalhos))
        for comeco, resposta in self.respostas.items():
            if url.startswith(comeco):
                return resposta
        raise AssertionError(f"pedido inesperado: {metodo} {url}")


def _token(valor: str = "token-da-vm") -> tuple[int, bytes]:
    return 200, json.dumps({"access_token": valor}).encode()


def test_segredo_e_lido_com_o_token_da_identidade_da_vm() -> None:
    transporte = Transporte(
        {
            IMDS: _token(),
            "https://cofre.vault.azure.net/secrets/PROXY-SEGREDO": (
                200,
                json.dumps({"value": MARCA}).encode(),
            ),
        }
    )

    valor = Azure(transporte).ler_segredo("cofre", "PROXY-SEGREDO")

    assert valor == MARCA
    metodo, url, cabecalhos = transporte.pedidos[0]
    # O token vem do serviço de metadados da própria VM: não existe senha nem chave para isso.
    assert (metodo, cabecalhos) == ("GET", {"Metadata": "true"})
    assert "resource=https%3A%2F%2Fvault.azure.net" in url
    assert transporte.pedidos[1][2]["Authorization"] == "Bearer token-da-vm"


def test_segredo_que_nao_existe_e_none() -> None:
    transporte = Transporte({IMDS: _token(), "https://cofre.vault.azure.net/": (404, b"{}")})

    assert Azure(transporte).ler_segredo("cofre", "NAO-EXISTE") is None


def test_cofre_recusando_vira_erro_sem_o_corpo_da_resposta() -> None:
    transporte = Transporte(
        {IMDS: _token(), "https://cofre.vault.azure.net/": (403, MARCA.encode())}
    )

    with pytest.raises(ErroDoAzure) as erro:
        Azure(transporte).ler_segredo("cofre", "PROXY-SEGREDO")

    assert "403" in str(erro.value)
    assert MARCA not in str(erro.value)


def test_o_token_e_pedido_uma_vez_por_servico() -> None:
    transporte = Transporte(
        {IMDS: _token(), "https://cofre.vault.azure.net/": (200, b'{"value": "x"}')}
    )
    azure = Azure(transporte)

    azure.ler_segredo("cofre", "A")
    azure.ler_segredo("cofre", "B")

    assert sum(url.startswith(IMDS) for _, url, _ in transporte.pedidos) == 1


BLOBS = "https://conta.blob.core.windows.net/backups"
LISTA = b"""<?xml version="1.0" encoding="utf-8"?>
<EnumerationResults ServiceEndpoint="https://conta.blob.core.windows.net/" ContainerName="backups">
  <Blobs>
    <Blob><Name>verifyscan-20261209T060000Z.dump</Name>
      <Properties><Last-Modified>Wed, 09 Dec 2026 06:00:03 GMT</Last-Modified></Properties></Blob>
    <Blob><Name>verifyscan-20261210T060000Z.dump</Name>
      <Properties><Last-Modified>Thu, 10 Dec 2026 06:00:02 GMT</Last-Modified></Properties></Blob>
  </Blobs>
  <NextMarker />
</EnumerationResults>"""


def test_enviar_blob_usa_o_token_do_armazenamento_e_os_cabecalhos_da_api() -> None:
    transporte = Transporte({IMDS: _token("token-de-blob"), BLOBS: (201, b"")})

    Azure(transporte).enviar_blob("conta", "backups", "verifyscan-x.dump", b"dump")

    assert "resource=https%3A%2F%2Fstorage.azure.com%2F" in transporte.pedidos[0][1]
    metodo, url, cabecalhos = transporte.pedidos[1]
    assert (metodo, url) == ("PUT", f"{BLOBS}/verifyscan-x.dump")
    assert cabecalhos["Authorization"] == "Bearer token-de-blob"
    assert cabecalhos["x-ms-blob-type"] == "BlockBlob"
    assert cabecalhos["x-ms-version"] and cabecalhos["x-ms-date"].endswith("GMT")


def test_listar_blobs_le_o_nome_e_a_data_de_cada_um() -> None:
    transporte = Transporte({IMDS: _token(), BLOBS: (200, LISTA)})

    blobs = Azure(transporte).listar_blobs("conta", "backups")

    assert [b.nome for b in blobs] == [
        "verifyscan-20261209T060000Z.dump",
        "verifyscan-20261210T060000Z.dump",
    ]
    assert blobs[1].modificado.isoformat() == "2026-12-10T06:00:02+00:00"
    assert transporte.pedidos[1][1] == f"{BLOBS}?restype=container&comp=list"


def test_baixar_e_apagar_blob() -> None:
    baixar = Transporte({IMDS: _token(), BLOBS: (200, b"dump")})
    assert Azure(baixar).baixar_blob("conta", "backups", "a.dump") == b"dump"

    apagar = Transporte({IMDS: _token(), BLOBS: (202, b"")})
    Azure(apagar).apagar_blob("conta", "backups", "a.dump")
    assert apagar.pedidos[1][0] == "DELETE"


def test_armazenamento_recusando_vira_erro_com_o_status() -> None:
    transporte = Transporte({IMDS: _token(), BLOBS: (403, b"AuthorizationPermissionMismatch")})

    with pytest.raises(ErroDoAzure, match="403"):
        Azure(transporte).enviar_blob("conta", "backups", "a.dump", b"dump")


def test_sem_identidade_o_erro_diz_que_o_token_falhou() -> None:
    transporte = Transporte({IMDS: (400, b"identity not found")})

    with pytest.raises(ErroDoAzure, match="token"):
        Azure(transporte).ler_segredo("cofre", "A")
