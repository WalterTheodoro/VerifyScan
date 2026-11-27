"""Ver os logs da produção sem SSH (ADR-0029, docs/deploy.md). A pedido, pelo run-command:

    python3 -m vm.logs <sha> <alvo> [texto]

O alvo é um serviço do compose (`backend`, `frontend`, `caddy`, `postgres`) ou `backup` (o que
o backup diário escreveu). Com o texto, saem só as linhas que o contêm: é como se segue uma
requisição, pelo `X-Request-ID` dela (docs/observabilidade.md).

O run-command devolve só os últimos 4 KB da saída. Por isso saem as linhas mais recentes que
cabem nesse espaço, inteiras; para ver mais para trás, filtre.

Os logs levam só metadado (CLAUDE.md §5, invariante 2), e o do Caddy sai sem o pedido
(`infra/Caddyfile`): não há IP, mensagem nem segredo para aparecer aqui.
"""

import sys

from vm.sistema import ComandoFalhou, Executar, dizer, executar_de_verdade

SERVICOS = ("backend", "frontend", "caddy", "postgres")
BACKUP = "backup"
# Abaixo dos 4096 bytes do run-command, com folga para o que ele mesmo escreve em volta.
LIMITE_DE_BYTES = 3500
# Até onde olhar para trás antes de filtrar.
_LINHAS = "5000"


def _comando(alvo: str) -> list[str] | None:
    if alvo == BACKUP:
        return [
            "journalctl",
            "--unit",
            "verifyscan-backup.service",
            "--no-pager",
            "--output",
            "short-iso",
            "--lines",
            _LINHAS,
        ]
    if alvo in SERVICOS:
        # O `docker logs` devolve em duas saídas o que o contêiner escreveu em cada uma, e os
        # logs do backend vão pela de erro. O `2>&1` junta as duas, na ordem. O nome do contêiner
        # entra como argumento ("$1"), nunca colado no texto do comando.
        conteiner = f"verifyscan-producao-{alvo}-1"
        return ["sh", "-c", 'docker logs --tail "$2" "$1" 2>&1', "sh", conteiner, _LINHAS]
    return None


def mostrar(alvo: str, filtro: str | None, *, executar: Executar) -> int:
    comando = _comando(alvo)
    if comando is None:
        dizer(f"LOGS_RECUSADO: o alvo tem de ser um destes: {', '.join((*SERVICOS, BACKUP))}.")
        return 2
    try:
        saida = executar(comando, {}, None).decode(errors="replace")
    except ComandoFalhou as erro:
        dizer(f"LOGS_FALHOU: não deu para ler os logs de {alvo} (código {erro.codigo}).")
        return 1

    linhas = [linha for linha in saida.splitlines() if filtro is None or filtro in linha]
    # Do fim para o começo, enquanto couber.
    escolhidas: list[str] = []
    ocupado = 0
    for linha in reversed(linhas):
        tamanho = len(linha.encode()) + 1
        if ocupado + tamanho > LIMITE_DE_BYTES:
            break
        escolhidas.append(linha)
        ocupado += tamanho
    for linha in reversed(escolhidas):
        dizer(linha)
    return 0


def main() -> int:
    # O primeiro argumento é o SHA, que o `entrar.sh` sempre passa.
    if len(sys.argv) < 3:
        dizer("uso: python3 -m vm.logs <sha> <alvo> [texto]")
        return 2
    filtro = sys.argv[3] if len(sys.argv) > 3 else None
    return mostrar(sys.argv[2], filtro, executar=executar_de_verdade)


if __name__ == "__main__":
    sys.exit(main())
