"""Como o backup, a restauração e a migração rodam comandos na VM (ADR-0029).

Um tipo só, para os testes trocarem por um falso (CLAUDE.md §6): o comando, variáveis de ambiente
a mais e o que entra pela entrada padrão; volta o que saiu pela saída padrão.

Segredo nunca vai no comando (a linha de comando aparece na lista de processos da máquina):
vai no ambiente, e o Docker o repassa ao contêiner com `-e NOME`, sem o valor.
"""

import os
import subprocess
from collections.abc import Callable, Mapping

Executar = Callable[[list[str], Mapping[str, str], bytes | None], bytes]

# Os contêineres da produção, pelos nomes que o compose dá (projeto `verifyscan-producao`).
POSTGRES = "verifyscan-producao-postgres-1"
SITE = ["verifyscan-producao-frontend-1", "verifyscan-producao-backend-1"]
REDE = "verifyscan-producao_default"


class ComandoFalhou(Exception):
    """O comando saiu com erro. Guarda o que ele escreveu na saída de erro, para quem chamou
    decidir o que pode ser mostrado."""

    def __init__(self, codigo: int, erro: str) -> None:
        super().__init__(f"O comando saiu com o código {codigo}.")
        self.codigo = codigo
        self.erro = erro


def executar_de_verdade(
    comando: list[str], ambiente: Mapping[str, str], entrada: bytes | None
) -> bytes:
    resultado = subprocess.run(
        comando,
        env={**os.environ, **ambiente},
        input=entrada,
        capture_output=True,
        check=False,
    )
    if resultado.returncode != 0:
        raise ComandoFalhou(resultado.returncode, resultado.stderr.decode(errors="replace"))
    return resultado.stdout


def dizer(texto: str) -> None:
    print(texto, flush=True)
