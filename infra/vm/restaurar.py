"""Restaurar o banco a partir de um backup (ADR-0029, docs/deploy.md). Só a pedido, pelo
run-command:

    python3 -m vm.restaurar <sha> [nome do backup]

Sem o nome, usa o backup mais recente. APAGA o que está no banco e põe no lugar o que estava no
backup: tudo o que foi gravado depois dele se perde.

O site é parado durante a restauração (ninguém grava no meio) e religado no fim, mesmo se ela
falhar. A restauração roda numa transação só: se falhar no meio, o banco fica como estava.

No fim, mostra quantas linhas ficaram em cada tabela e a versão do alembic, com a mesma consulta
da migração (`vm/contagem.py`): é o que se confere contra o que se esperava da cópia.

Se falhar, avisa pelo Sentry (`vm/alerta.py`). Backup que não existe não é falha: é recusa, e a
resposta já sai na hora para quem pediu.
"""

import sys

from vm import config, contagem
from vm.alerta import Avisar, com_aviso
from vm.azure import Azure, ErroDoAzure
from vm.backup import PREFIXO, Armazenamento
from vm.sistema import POSTGRES, SITE, ComandoFalhou, Executar, dizer, executar_de_verdade

O_QUE = "A restauração do banco falhou"


def _contar(executar: Executar) -> dict[str, str] | None:
    """As contagens do banco, pelo psql do próprio contêiner. Sem conseguir contar, devolve
    None: a restauração já terminou, e isso não a desfaz."""
    comando = [
        "docker",
        "exec",
        "-i",
        POSTGRES,
        "sh",
        "-c",
        f"{contagem.PSQL} --username=verifyscan --dbname=verifyscan",
    ]
    try:
        return contagem.ler(executar(comando, {}, contagem.CONSULTA.encode()))
    except ComandoFalhou:
        return None


def restaurar(
    nome: str | None, *, executar: Executar, armazenamento: Armazenamento, avisar: Avisar
) -> int:
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
        dizer(f"RESTAURACAO_FALHOU: nada foi tocado. {erro}")
        avisar(str(erro))
        return 1

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
        # Com o site ainda parado: é o retrato exato do que veio da cópia.
        contagens = _contar(executar)
    except ComandoFalhou as erro:
        # O erro do Postgres fica no log da VM, para quem pediu; ao aviso vai só o código.
        dizer(f"RESTAURACAO_FALHOU: o banco ficou como estava. {erro.erro.strip()}")
        avisar(f"o pg_restore saiu com o código {erro.codigo}.")
        return 1
    finally:
        executar(["docker", "start", *SITE], {}, None)
    if contagens is None:
        dizer("Aviso: não deu para contar as linhas depois da restauração.")
        dizer(f"RESTAURACAO_OK: o banco voltou ao estado de {nome}.")
        return 0
    dizer(f"{'tabela':<28}{'linhas':>10}")
    for tabela in sorted(contagens):
        dizer(f"{tabela:<28}{contagens[tabela]:>10}")
    dizer(
        f"RESTAURACAO_OK: o banco voltou ao estado de {nome}; "
        f"{len(contagens) - 1} tabelas, alembic em {contagens.get('alembic')}."
    )
    return 0


def main() -> int:
    # O primeiro argumento é o SHA, que o `entrar.sh` sempre passa; o segundo, o nome do backup.
    nome = sys.argv[2] if len(sys.argv) > 2 else None
    azure = Azure()
    return com_aviso(
        O_QUE,
        lambda avisar: restaurar(
            nome, executar=executar_de_verdade, armazenamento=azure, avisar=avisar
        ),
        cofre=azure,
    )


if __name__ == "__main__":
    sys.exit(main())
