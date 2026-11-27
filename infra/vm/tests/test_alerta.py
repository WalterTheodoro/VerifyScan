"""O aviso de falha ao Sentry, com o cofre e a rede falsos."""

import json
from datetime import UTC, datetime

import pytest

from vm import alerta, config
from vm.azure import ErroDoAzure

AGORA = datetime(2026, 12, 10, 6, 0, 5, tzinfo=UTC)
DSN = "https://chaveMARCA@o123.ingest.us.sentry.io/456"
ENVELOPE = "https://o123.ingest.us.sentry.io/api/456/envelope/"


class Cofre:
    def __init__(self, dsn: str | None = DSN, erro: Exception | None = None) -> None:
        self.dsn = dsn
        self.erro = erro

    def ler_segredo(self, cofre: str, nome: str) -> str | None:
        assert (cofre, nome) == (config.COFRE, "SENTRY-DSN")
        if self.erro is not None:
            raise self.erro
        return self.dsn


class Rede:
    def __init__(self, status: int = 200, erro: Exception | None = None) -> None:
        self.status = status
        self.erro = erro
        self.pedidos: list[tuple[str, str, dict[str, str], bytes | None]] = []

    def __call__(
        self, metodo: str, url: str, cabecalhos: dict[str, str], corpo: bytes | None
    ) -> tuple[int, bytes]:
        self.pedidos.append((metodo, url, cabecalhos, corpo))
        if self.erro is not None:
            raise self.erro
        return self.status, b'{"id": "x"}'


def _avisar(cofre: Cofre, rede: Rede, motivo: str = "o pg_dump saiu com o código 1") -> bool:
    return alerta.avisar_falha(
        "O backup do banco falhou", motivo, cofre=cofre, pedir=rede, agora=AGORA
    )


def test_o_evento_vai_ao_endereco_do_dsn_com_a_chave_no_cabecalho() -> None:
    rede = Rede()

    assert _avisar(Cofre(), rede) is True

    metodo, url, cabecalhos, _ = rede.pedidos[0]
    assert (metodo, url) == ("POST", ENVELOPE)
    assert "sentry_version=7" in cabecalhos["X-Sentry-Auth"]
    assert "sentry_key=chaveMARCA" in cabecalhos["X-Sentry-Auth"]
    assert cabecalhos["Content-Type"] == "application/x-sentry-envelope"


def test_o_evento_leva_so_o_que_falhou_e_o_motivo() -> None:
    rede = Rede()

    _avisar(Cofre(), rede)

    corpo = rede.pedidos[0][3]
    assert corpo is not None
    cabecalho, item, carga = corpo.rstrip(b"\n").split(b"\n")
    evento = json.loads(carga)
    # O formato do envelope: o id do evento repetido no cabeçalho, e o tamanho exato da carga.
    assert json.loads(cabecalho)["event_id"] == evento["event_id"]
    assert len(evento["event_id"]) == 32
    assert json.loads(item) == {"type": "event", "length": len(carga)}
    assert evento["logentry"] == {
        "formatted": "O backup do banco falhou: o pg_dump saiu com o código 1"
    }
    assert evento["level"] == "error"
    # O mesmo ambiente do backend, para cair na mesma regra de e-mail.
    assert evento["environment"] == "producao"
    # Nada além disso: nem quem, nem de onde, nem o DSN (que vai só no cabeçalho do pedido).
    assert set(evento) == {
        "event_id",
        "timestamp",
        "platform",
        "level",
        "logger",
        "environment",
        "logentry",
        "fingerprint",
        "tags",
    }
    assert b"MARCA" not in corpo


def test_dsn_com_caminho_antes_do_projeto() -> None:
    rede = Rede()

    _avisar(Cofre("https://chave@sentry.exemplo.invalid/prefixo/7"), rede)

    assert rede.pedidos[0][1] == "https://sentry.exemplo.invalid/prefixo/api/7/envelope/"


@pytest.mark.parametrize("dsn", [None, "", "  ", config.A_PREENCHER])
def test_sem_dsn_no_cofre_so_registra_no_log(
    dsn: str | None, capsys: pytest.CaptureFixture[str]
) -> None:
    rede = Rede()

    assert _avisar(Cofre(dsn), rede) is False

    assert rede.pedidos == []
    assert "AVISO_NAO_ENVIADO" in capsys.readouterr().out


@pytest.mark.parametrize(
    "caso",
    ["o sentry responde 500", "a rede cai", "o cofre recusa", "o dsn está errado"],
)
def test_o_aviso_que_falha_nunca_derruba_quem_avisou(
    caso: str, capsys: pytest.CaptureFixture[str]
) -> None:
    cofre, rede = Cofre(), Rede()
    if caso == "o sentry responde 500":
        rede = Rede(status=500)
    elif caso == "a rede cai":
        rede = Rede(erro=OSError(f"sem rota para {DSN}"))
    elif caso == "o cofre recusa":
        cofre = Cofre(erro=ErroDoAzure("O cofre respondeu 403 ao ler SENTRY-DSN."))
    else:
        cofre = Cofre("MARCA-isto-nao-e-um-dsn")

    assert _avisar(cofre, rede) is False

    saida = capsys.readouterr().out
    assert "AVISO_NAO_ENVIADO" in saida
    # Nem o DSN nem a mensagem da exceção (que pode trazê-lo) vão para o log.
    assert "MARCA" not in saida


def test_erro_inesperado_avisa_com_o_tipo_sem_a_mensagem_e_segue_sendo_erro() -> None:
    rede = Rede()

    def tarefa(avisar: alerta.Avisar) -> int:
        raise TimeoutError("postgresql://dono:senha_MARCA@host/banco")

    with pytest.raises(TimeoutError):
        alerta.com_aviso("O backup do banco falhou", tarefa, cofre=Cofre(), pedir=rede)

    corpo = rede.pedidos[0][3]
    assert corpo is not None
    assert b"erro inesperado (TimeoutError)" in corpo
    assert b"senha_MARCA" not in corpo


def test_tarefa_que_termina_bem_nao_avisa() -> None:
    rede = Rede()

    codigo = alerta.com_aviso("O backup do banco falhou", lambda _: 0, cofre=Cofre(), pedir=rede)

    assert codigo == 0
    assert rede.pedidos == []
