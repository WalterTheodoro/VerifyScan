"""Ver os logs da VM pelo run-command, com o Docker falso."""

from collections.abc import Mapping

import pytest

from vm import logs
from vm.sistema import ComandoFalhou


class Sistema:
    def __init__(self, saida: str = "", quebra: bool = False) -> None:
        self.comandos: list[list[str]] = []
        self.saida = saida
        self.quebra = quebra

    def __call__(
        self, comando: list[str], ambiente: Mapping[str, str], entrada: bytes | None
    ) -> bytes:
        self.comandos.append(comando)
        if self.quebra:
            raise ComandoFalhou(1, "No such container")
        return self.saida.encode()


def test_log_de_um_servico_vem_do_conteiner_dele(capsys: pytest.CaptureFixture[str]) -> None:
    sistema = Sistema("linha 1\nlinha 2\n")

    codigo = logs.mostrar("backend", None, executar=sistema)

    assert codigo == 0
    assert "verifyscan-producao-backend-1" in sistema.comandos[0]
    assert capsys.readouterr().out.splitlines() == ["linha 1", "linha 2"]


def test_log_do_backup_vem_do_systemd() -> None:
    sistema = Sistema("BACKUP_OK\n")

    logs.mostrar("backup", None, executar=sistema)

    assert sistema.comandos[0][0] == "journalctl"
    assert "verifyscan-backup.service" in sistema.comandos[0]


def test_com_filtro_so_saem_as_linhas_que_o_contem(capsys: pytest.CaptureFixture[str]) -> None:
    """É como se segue uma requisição: o filtro é o X-Request-ID dela."""
    sistema = Sistema(
        '{"request_id": "abc"}\n{"request_id": "xyz"}\n{"request_id": "abc", "n": 2}\n'
    )

    logs.mostrar("backend", "abc", executar=sistema)

    saida = capsys.readouterr().out.splitlines()
    assert len(saida) == 2 and all("abc" in linha for linha in saida)
    # O filtro nunca entra no comando: é texto comparado aqui, não trecho de shell.
    assert all("abc" not in parte for parte in sistema.comandos[0])


def test_saem_as_linhas_mais_recentes_que_cabem_inteiras(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """O run-command devolve só o fim da saída: melhor poucas linhas inteiras que uma cortada."""
    linhas = [f"{numero:04d} " + "x" * 95 for numero in range(200)]
    sistema = Sistema("\n".join(linhas) + "\n")

    logs.mostrar("backend", None, executar=sistema)

    saida = capsys.readouterr().out
    assert len(saida.encode()) <= logs.LIMITE_DE_BYTES
    mostradas = saida.splitlines()
    assert mostradas[-1] == linhas[-1]
    assert mostradas == linhas[-len(mostradas) :]


@pytest.mark.parametrize("alvo", ["", "outro", "backend; rm -rf /", "../x"])
def test_alvo_desconhecido_e_recusado_sem_rodar_nada(alvo: str) -> None:
    sistema = Sistema()

    assert logs.mostrar(alvo, None, executar=sistema) != 0
    assert sistema.comandos == []


def test_conteiner_que_nao_existe_vira_recusa_e_nao_erro(
    capsys: pytest.CaptureFixture[str],
) -> None:
    codigo = logs.mostrar("backend", None, executar=Sistema(quebra=True))

    assert codigo != 0
    assert "LOGS_FALHOU" in capsys.readouterr().out
