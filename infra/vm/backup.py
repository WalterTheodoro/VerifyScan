"""O backup diário do banco (ADR-0029). Roda na VM, pelo agendamento do systemd
(`vm/systemd/verifyscan-backup.timer`) ou, a pedido, pelo run-command:

    python3 -m vm.backup

O `pg_dump` sai do contêiner do Postgres direto para a memória deste processo e daí para o
armazenamento do Azure, com a identidade da VM: a cópia do banco nunca vira arquivo na VM.

Guarda 7 dias. Depois de gravar a cópia nova, apaga as que têm 7 dias ou mais: é o que o aviso
de privacidade promete (o que a pessoa apagou some das cópias em até 7 dias). A regra de
exclusão do próprio armazenamento (`infra/main.bicep`) fica como rede de segurança, para o caso
de a VM passar dias parada.
"""

import sys
from datetime import UTC, datetime, timedelta
from typing import Protocol

from vm import config
from vm.azure import Azure, Blob, ErroDoAzure
from vm.sistema import POSTGRES, ComandoFalhou, Executar, dizer, executar_de_verdade

PREFIXO = "verifyscan-"
GUARDAR = timedelta(days=7)


class Armazenamento(Protocol):
    def enviar_blob(self, conta: str, container: str, nome: str, conteudo: bytes) -> None: ...
    def listar_blobs(self, conta: str, container: str) -> list[Blob]: ...
    def baixar_blob(self, conta: str, container: str, nome: str) -> bytes: ...
    def apagar_blob(self, conta: str, container: str, nome: str) -> None: ...


def nome_do_backup(agora: datetime) -> str:
    return f"{PREFIXO}{agora:%Y%m%dT%H%M%SZ}.dump"


def fazer_backup(agora: datetime, *, executar: Executar, armazenamento: Armazenamento) -> int:
    conta, container = config.CONTA_DE_ARMAZENAMENTO, config.CONTAINER_DE_BACKUPS
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
            dizer("BACKUP_FALHOU: o pg_dump não devolveu nada.")
            return 1
        nome = nome_do_backup(agora)
        armazenamento.enviar_blob(conta, container, nome, dump)
    except (ComandoFalhou, ErroDoAzure) as erro:
        dizer(f"BACKUP_FALHOU: {erro}")
        return 1

    # Só depois de a cópia nova estar guardada: nunca fica sem cópia nenhuma.
    apagados = 0
    try:
        for blob in armazenamento.listar_blobs(conta, container):
            if blob.nome.startswith(PREFIXO) and agora - blob.modificado >= GUARDAR:
                armazenamento.apagar_blob(conta, container, blob.nome)
                apagados += 1
    except ErroDoAzure as erro:
        dizer(f"BACKUP_INCOMPLETO: {nome} foi gravado, mas a limpeza das antigas falhou: {erro}")
        return 1
    dizer(f"BACKUP_OK: {nome}, {len(dump)} bytes; cópias antigas apagadas: {apagados}.")
    return 0


def main() -> int:
    return fazer_backup(datetime.now(UTC), executar=executar_de_verdade, armazenamento=Azure())


if __name__ == "__main__":
    sys.exit(main())
