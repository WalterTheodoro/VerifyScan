"""Restaurar o banco a partir de um backup (ADR-0029, docs/deploy.md). Só a pedido, pelo
run-command:

    python3 -m vm.restaurar <sha> [nome do backup]

Sem o nome, usa o backup mais recente. APAGA o que está no banco e põe no lugar o que estava no
backup: tudo o que foi gravado depois dele se perde.

O site é parado durante a restauração (ninguém grava no meio) e religado no fim, mesmo se ela
falhar. A restauração roda numa transação só: se falhar no meio, o banco fica como estava.
"""

import sys

from vm import config
from vm.azure import Azure, ErroDoAzure
from vm.backup import PREFIXO, Armazenamento
from vm.sistema import POSTGRES, SITE, ComandoFalhou, Executar, dizer, executar_de_verdade


def restaurar(nome: str | None, *, executar: Executar, armazenamento: Armazenamento) -> int:
    conta, container = config.CONTA_DE_ARMAZENAMENTO, config.CONTAINER_DE_BACKUPS
    try:
        backups = [
            b for b in armazenamento.listar_blobs(conta, container) if b.nome.startswith(PREFIXO)
        ]
        if nome is None and backups:
            nome = max(backups, key=lambda b: b.modificado).nome
        if nome is None or nome not in {b.nome for b in backups}:
            disponiveis = ", ".join(sorted(b.nome for b in backups)) or "nenhum"
            dizer(f"RESTAURACAO_RECUSADA: backup não encontrado. Disponíveis: {disponiveis}.")
            return 2
        dump = armazenamento.baixar_blob(conta, container, nome)
    except ErroDoAzure as erro:
        dizer(f"RESTAURACAO_RECUSADA: {erro}")
        return 2

    dizer(f"Restaurando {nome} ({len(dump)} bytes). O site fica parado durante a restauração.")
    executar(["docker", "stop", *SITE], {}, None)
    try:
        executar(
            [
                "docker",
                "exec",
                "-i",
                POSTGRES,
                "pg_restore",
                "--username=verifyscan",
                "--dbname=verifyscan",
                "--clean",
                "--if-exists",
                "--no-owner",
                "--single-transaction",
            ],
            {},
            dump,
        )
    except ComandoFalhou as erro:
        dizer(f"RESTAURACAO_FALHOU: o banco ficou como estava. {erro.erro.strip()}")
        return 1
    finally:
        executar(["docker", "start", *SITE], {}, None)
    dizer(f"RESTAURACAO_OK: o banco voltou ao estado de {nome}.")
    return 0


def main() -> int:
    # O primeiro argumento é o SHA, que o `entrar.sh` sempre passa; o segundo, o nome do backup.
    nome = sys.argv[2] if len(sys.argv) > 2 else None
    return restaurar(nome, executar=executar_de_verdade, armazenamento=Azure())


if __name__ == "__main__":
    sys.exit(main())
