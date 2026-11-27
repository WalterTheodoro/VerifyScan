"""O backup diário do banco (ADR-0029). Roda na VM, pelo agendamento do systemd
(`vm/systemd/verifyscan-backup.timer`) ou, a pedido, pelo run-command:

    python3 -m vm.backup

O `pg_dump` sai do contêiner do Postgres direto para a memória deste processo e daí para o
armazenamento do Azure, com a identidade da VM: a cópia do banco nunca vira arquivo na VM.

Guarda 7 dias. Depois de gravar a cópia nova, apaga as que têm 7 dias ou mais: é o que o aviso
de privacidade promete (o que a pessoa apagou some das cópias em até 7 dias). A regra de
exclusão do próprio armazenamento (`infra/main.bicep`) fica como rede de segurança, para o caso
de a VM passar dias parada.

Se falhar, avisa pelo Sentry (`vm/alerta.py`), além de registrar no log da VM.
"""

import sys
from datetime import UTC, datetime, timedelta
from typing import Protocol

from vm import config
from vm.alerta import Avisar, com_aviso
from vm.azure import Azure, Blob, ErroDoAzure
from vm.sistema import POSTGRES, ComandoFalhou, Executar, dizer, executar_de_verdade

PREFIXO = "verifyscan-"
GUARDAR = timedelta(days=7)
O_QUE = "O backup do banco falhou"


class Armazenamento(Protocol):
    def enviar_blob(self, conta: str, container: str, nome: str, conteudo: bytes) -> None: ...
    def listar_blobs(self, conta: str, container: str) -> list[Blob]: ...
    def baixar_blob(self, conta: str, container: str, nome: str) -> bytes: ...
    def apagar_blob(self, conta: str, container: str, nome: str) -> None: ...


def nome_do_backup(agora: datetime) -> str:
    return f"{PREFIXO}{agora:%Y%m%dT%H%M%SZ}.dump"


def fazer_backup(
    agora: datetime, *, executar: Executar, armazenamento: Armazenamento, avisar: Avisar
) -> int:
    conta, container = config.CONTA_DE_ARMAZENAMENTO, config.CONTAINER_DE_BACKUPS

    def falhou(marca: str, motivo: str) -> int:
        dizer(f"{marca}: {motivo}")
        avisar(motivo)
        return 1

    try:
        # Formato próprio do Postgres (compactado), o que o `pg_restore` lê.
        dump = executar(
            [
                "docker",
                "exec",
                POSTGRES,
                "pg_dump",
                "--username=verifyscan",
                "--format=custom",
                "verifyscan",
            ],
            {},
            None,
        )
        if not dump:
            return falhou("BACKUP_FALHOU", "o pg_dump não devolveu nada.")
        nome = nome_do_backup(agora)
        armazenamento.enviar_blob(conta, container, nome, dump)
    except ComandoFalhou as erro:
        # Só o código de saída: o que o Postgres escreveu no erro não vai para o aviso.
        return falhou("BACKUP_FALHOU", f"o pg_dump saiu com o código {erro.codigo}.")
    except ErroDoAzure as erro:
        return falhou("BACKUP_FALHOU", str(erro))

    # Só depois de a cópia nova estar guardada: nunca fica sem cópia nenhuma.
    apagados = 0
    try:
        for blob in armazenamento.listar_blobs(conta, container):
            if blob.nome.startswith(PREFIXO) and agora - blob.modificado >= GUARDAR:
                armazenamento.apagar_blob(conta, container, blob.nome)
                apagados += 1
    except ErroDoAzure as erro:
        return falhou(
            "BACKUP_INCOMPLETO",
            f"a cópia nova foi gravada, mas a limpeza das antigas falhou. {erro}",
        )
    dizer(f"BACKUP_OK: {nome}, {len(dump)} bytes; cópias antigas apagadas: {apagados}.")
    return 0


def main() -> int:
    azure = Azure()
    return com_aviso(
        O_QUE,
        lambda avisar: fazer_backup(
            datetime.now(UTC), executar=executar_de_verdade, armazenamento=azure, avisar=avisar
        ),
        cofre=azure,
    )


if __name__ == "__main__":
    sys.exit(main())
