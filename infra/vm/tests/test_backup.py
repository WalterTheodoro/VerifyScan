"""O backup diário e a restauração, com o Docker e o armazenamento falsos."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import pytest

from vm import backup, config, restaurar
from vm.azure import Blob, ErroDoAzure
from vm.sistema import ComandoFalhou

AGORA = datetime(2026, 12, 10, 6, 0, 0, tzinfo=UTC)
DUMP = b"PGDMP-conteudo-do-banco"


class Armazenamento:
    def __init__(self, blobs: dict[str, tuple[datetime, bytes]] | None = None) -> None:
        self.blobs = dict(blobs or {})
        self.recusa_envio = False

    def enviar_blob(self, conta: str, container: str, nome: str, conteudo: bytes) -> None:
        assert (conta, container) == (config.CONTA_DE_ARMAZENAMENTO, config.CONTAINER_DE_BACKUPS)
        if self.recusa_envio:
            raise ErroDoAzure("O armazenamento respondeu 503 (PUT).")
        self.blobs[nome] = (AGORA, conteudo)

    def listar_blobs(self, conta: str, container: str) -> list[Blob]:
        return [Blob(nome, quando) for nome, (quando, _) in self.blobs.items()]

    def baixar_blob(self, conta: str, container: str, nome: str) -> bytes:
        return self.blobs[nome][1]

    def apagar_blob(self, conta: str, container: str, nome: str) -> None:
        del self.blobs[nome]


class Docker:
    def __init__(self, dump: bytes = DUMP, quebra: str | None = None) -> None:
        self.comandos: list[tuple[list[str], bytes | None]] = []
        self.dump = dump
        self.quebra = quebra

    def __call__(
        self, comando: list[str], ambiente: Mapping[str, str], entrada: bytes | None
    ) -> bytes:
        self.comandos.append((comando, entrada))
        if self.quebra is not None and self.quebra in comando:
            raise ComandoFalhou(1, "erro")
        return self.dump if "pg_dump" in comando else b""


def _antigo(dias: float) -> tuple[datetime, bytes]:
    return AGORA - timedelta(days=dias), b"velho"


# ─── backup ───────────────────────────────────────────────────────────────────────────────


def test_backup_manda_o_dump_com_a_data_no_nome() -> None:
    armazenamento = Armazenamento()
    docker = Docker()

    codigo = backup.fazer_backup(AGORA, executar=docker, armazenamento=armazenamento)

    assert codigo == 0
    assert armazenamento.blobs["verifyscan-20261210T060000Z.dump"][1] == DUMP
    comando = docker.comandos[0][0]
    assert comando[:3] == ["docker", "exec", "verifyscan-producao-postgres-1"]
    assert "pg_dump" in comando and "--format=custom" in comando


def test_backup_apaga_o_que_tem_7_dias_ou_mais_e_so_isso() -> None:
    """O aviso de privacidade promete: o que a pessoa apagou some das cópias em até 7 dias."""
    armazenamento = Armazenamento(
        {
            "verifyscan-a.dump": _antigo(7),
            "verifyscan-b.dump": _antigo(9),
            "verifyscan-c.dump": _antigo(6.9),
            "outro-arquivo.txt": _antigo(30),
        }
    )

    backup.fazer_backup(AGORA, executar=Docker(), armazenamento=armazenamento)

    assert sorted(armazenamento.blobs) == [
        "outro-arquivo.txt",  # não é nosso: não é tocado
        "verifyscan-20261210T060000Z.dump",
        "verifyscan-c.dump",
    ]


@pytest.mark.parametrize("falha", ["dump vazio", "pg_dump falhou", "envio recusado"])
def test_backup_que_falha_nao_apaga_nenhum_antigo(falha: str) -> None:
    """Primeiro o novo chega; só depois os velhos saem. Nunca fica sem cópia nenhuma."""
    armazenamento = Armazenamento({"verifyscan-velho.dump": _antigo(8)})
    armazenamento.recusa_envio = falha == "envio recusado"
    docker = Docker(
        dump=b"" if falha == "dump vazio" else DUMP,
        quebra="pg_dump" if falha == "pg_dump falhou" else None,
    )

    codigo = backup.fazer_backup(AGORA, executar=docker, armazenamento=armazenamento)

    assert codigo != 0
    assert list(armazenamento.blobs) == ["verifyscan-velho.dump"]


# ─── restauração ──────────────────────────────────────────────────────────────────────────


def test_restaurar_sem_nome_usa_o_backup_mais_recente() -> None:
    armazenamento = Armazenamento(
        {
            "verifyscan-antigo.dump": (AGORA - timedelta(days=2), b"antigo"),
            "verifyscan-recente.dump": (AGORA - timedelta(days=1), b"recente"),
        }
    )
    docker = Docker()

    codigo = restaurar.restaurar(None, executar=docker, armazenamento=armazenamento)

    assert codigo == 0
    comando, entrada = next((c, e) for c, e in docker.comandos if "pg_restore" in c)
    assert entrada == b"recente"
    # Tudo ou nada: uma restauração que falha no meio deixa o banco como estava.
    assert "--single-transaction" in comando and "--clean" in comando


def test_restaurar_para_o_site_antes_e_o_religa_depois() -> None:
    armazenamento = Armazenamento({"verifyscan-x.dump": (AGORA, b"x")})
    docker = Docker()

    restaurar.restaurar("verifyscan-x.dump", executar=docker, armazenamento=armazenamento)

    passos = [c[1] if c[1] in ("stop", "start") else "restore" for c, _ in docker.comandos]
    assert passos == ["stop", "restore", "start"]


def test_restauracao_que_falha_religa_o_site_mesmo_assim() -> None:
    armazenamento = Armazenamento({"verifyscan-x.dump": (AGORA, b"x")})
    docker = Docker(quebra="pg_restore")

    codigo = restaurar.restaurar(None, executar=docker, armazenamento=armazenamento)

    assert codigo != 0
    assert docker.comandos[-1][0][:2] == ["docker", "start"]


def test_restaurar_backup_que_nao_existe_nao_para_o_site() -> None:
    docker = Docker()

    codigo = restaurar.restaurar("nao-existe.dump", executar=docker, armazenamento=Armazenamento())

    assert codigo != 0
    assert docker.comandos == []
