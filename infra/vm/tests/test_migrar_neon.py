"""A migração dos dados do Neon para o Postgres da VM, com o Docker e o cofre falsos."""

from collections.abc import Mapping

import pytest

from vm import config, migrar_neon
from vm.sistema import ComandoFalhou

URL_DO_NEON = "postgresql://dono_MARCA:senha_MARCA@ep-MARCA.us-west-2.aws.neon.tech/banco_MARCA?sslmode=require"
CONTAGEM = b"alembic|0008\nanalises|120\nindicadores_risco|431\nusuarios|9\n"


class Cofre:
    def __init__(self, segredos: Mapping[str, str]) -> None:
        self.segredos = dict(segredos)

    def ler_segredo(self, cofre: str, nome: str) -> str | None:
        assert cofre == config.COFRE
        return self.segredos.get(nome)


SEGREDOS = {"NEON-DATABASE-URL": URL_DO_NEON, "POSTGRES-PASSWORD": "senha-do-destino-MARCA"}


class Docker:
    """Responde às contagens (a da origem pode mudar entre a 1ª e a 2ª) e anota tudo."""

    def __init__(
        self,
        origem: list[bytes] | None = None,
        destino: bytes = CONTAGEM,
        erro_na_copia: str | None = None,
    ) -> None:
        self.comandos: list[tuple[list[str], dict[str, str]]] = []
        self.origem = list(origem or [CONTAGEM, CONTAGEM])
        self.destino = destino
        self.erro_na_copia = erro_na_copia

    def __call__(
        self, comando: list[str], ambiente: Mapping[str, str], entrada: bytes | None
    ) -> bytes:
        self.comandos.append((comando, dict(ambiente)))
        roteiro = comando[-1]
        if "pg_dump" in roteiro:
            if self.erro_na_copia is not None:
                raise ComandoFalhou(1, self.erro_na_copia)
            return b""
        if "psql" in roteiro:
            return self.origem.pop(0) if "$ORIGEM" in roteiro else self.destino
        return b""

    def passos(self) -> list[str]:
        nomes = []
        for comando, _ in self.comandos:
            if comando[1] in ("stop", "start"):
                nomes.append(comando[1])
            elif "pg_dump" in comando[-1]:
                nomes.append("copiar")
            else:
                nomes.append("contar origem" if "$ORIGEM" in comando[-1] else "contar destino")
        return nomes


def _migrar(docker: Docker, segredos: Mapping[str, str] = SEGREDOS) -> int:
    return migrar_neon.migrar(executar=docker, cofre=Cofre(segredos))


def test_migracao_copia_e_confere_as_contagens(capsys: pytest.CaptureFixture[str]) -> None:
    docker = Docker()

    codigo = _migrar(docker)

    assert codigo == 0
    assert docker.passos() == [
        "contar origem",
        "stop",
        "copiar",
        "contar origem",
        "contar destino",
        "start",
    ]
    saida = capsys.readouterr().out
    # A tabela da conferência, linha a linha, e a versão do alembic dos dois lados.
    assert "analises" in saida and "120" in saida
    assert "0008" in saida
    assert "MIGRACAO_OK" in saida


def test_a_string_do_neon_nunca_vai_para_o_comando_nem_para_a_saida(
    capsys: pytest.CaptureFixture[str],
) -> None:
    docker = Docker()

    _migrar(docker)

    impresso = capsys.readouterr()
    assert "MARCA" not in impresso.out + impresso.err
    for comando, _ in docker.comandos:
        assert "MARCA" not in " ".join(comando)
    # Ela vai só no ambiente do comando que precisa dela, e o Docker a repassa pelo nome.
    copiar = next((c, a) for c, a in docker.comandos if "pg_dump" in c[-1])
    assert copiar[1]["ORIGEM"] == URL_DO_NEON
    assert "ORIGEM" in copiar[0] and URL_DO_NEON not in copiar[0]


def test_contagem_diferente_reprova_e_mostra_onde(capsys: pytest.CaptureFixture[str]) -> None:
    docker = Docker(destino=CONTAGEM.replace(b"analises|120", b"analises|119"))

    codigo = _migrar(docker)

    assert codigo != 0
    saida = capsys.readouterr().out
    assert "MIGRACAO_FALHOU" in saida
    assert "analises" in saida and "119" in saida
    assert docker.passos()[-1] == "start"


def test_versao_do_alembic_diferente_reprova() -> None:
    docker = Docker(destino=CONTAGEM.replace(b"alembic|0008", b"alembic|0007"))

    assert _migrar(docker) != 0


def test_origem_que_mudou_durante_a_copia_reprova(capsys: pytest.CaptureFixture[str]) -> None:
    """O Render continua no ar na rodada de validação: se alguém gravou no Neon no meio da
    cópia, a comparação não vale e a migração é para rodar de novo."""
    depois = CONTAGEM.replace(b"analises|120", b"analises|121")
    docker = Docker(origem=[CONTAGEM, depois], destino=depois)

    codigo = _migrar(docker)

    assert codigo != 0
    assert "mudou durante" in capsys.readouterr().out


@pytest.mark.parametrize("falta", ["NEON-DATABASE-URL", "POSTGRES-PASSWORD"])
def test_sem_o_segredo_recusa_sem_parar_o_site(falta: str) -> None:
    docker = Docker()

    codigo = _migrar(docker, {k: v for k, v in SEGREDOS.items() if k != falta})

    assert codigo != 0
    assert docker.comandos == []


def test_erro_da_copia_e_mostrado_sem_host_usuario_senha_nem_banco(
    capsys: pytest.CaptureFixture[str],
) -> None:
    erro = (
        'pg_dump: error: connection to server at "ep-MARCA.us-west-2.aws.neon.tech" '
        "(203.0.113.9), port 5432 failed: FATAL: password authentication failed for user "
        '"dono_MARCA" database "banco_MARCA" senha_MARCA'
    )
    docker = Docker(erro_na_copia=erro)

    codigo = _migrar(docker)

    assert codigo != 0
    saida = capsys.readouterr().out
    assert "password authentication failed" in saida
    assert "MARCA" not in saida
    assert "203.0.113.9" not in saida
    assert docker.passos()[-1] == "start"
