"""O deploy na VM: a ordem dos passos, a recusa antes de tocar em contêiner, a volta automática
para a versão anterior e o cuidado com os segredos."""

import os
import stat
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

from vm import config, deploy

SHA_A = "a" * 40
SHA_B = "b" * 40
MARCA = "MARCA-DE-SEGREDO"

SEGREDOS = {
    "POSTGRES-PASSWORD": f"senha-{MARCA}",
    "IP-HMAC-SEGREDO": f"hmac-{MARCA}",
    "PROXY-SEGREDO": f"proxy-{MARCA}",
    "ANTHROPIC-API-KEY": f"chave-{MARCA}",
    "EMAIL-ACME": "contato@exemplo.invalid",
    "SENTRY-DSN": f"https://{MARCA}@o0.ingest.exemplo.invalid/1",
}


class CofreFalso:
    def __init__(self, segredos: Mapping[str, str]) -> None:
        self.segredos = dict(segredos)

    def ler_segredo(self, cofre: str, nome: str) -> str | None:
        assert cofre == config.COFRE
        return self.segredos.get(nome)


class Maquina:
    """No lugar do `subprocess`: anota cada comando e sabe qual versão está no ar. `quebra` diz
    qual passo falha, e em qual versão."""

    def __init__(self, quebra: tuple[str, str] | None = None) -> None:
        self.comandos: list[tuple[list[str], dict[str, str]]] = []
        self.no_ar: str | None = None
        self.quebra = quebra

    def __call__(self, comando: list[str], ambiente: Mapping[str, str]) -> None:
        self.comandos.append((comando, dict(ambiente)))
        passo = self._passo(comando)
        versao = ambiente.get("TAG", self.no_ar)
        if self.quebra == (passo, versao):
            raise subprocess.CalledProcessError(1, comando)
        if passo == "subir":
            self.no_ar = ambiente["TAG"]

    @staticmethod
    def _passo(comando: list[str]) -> str:
        if comando[0] == "curl":
            return "saude"
        if comando[0] == "systemctl":
            return "ssh" if "mask" in comando else "agendar"
        if "pull" in comando:
            return "baixar"
        if "alembic" in comando:
            return "migrar"
        if "postgres" in comando:
            return "banco"
        if "up" in comando:
            return "subir"
        return "outro"

    def passos(self) -> list[tuple[str, str | None]]:
        return [(self._passo(c), a.get("TAG")) for c, a in self.comandos]

    def do_docker(self) -> list[list[str]]:
        return [c for c, _ in self.comandos if c[0] == "docker"]


def _pasta(tmp_path: Path, *versoes: str, no_ar: str | None = None) -> Path:
    """A pasta do deploy como o `entrar.sh` a deixa: os arquivos de cada versão já baixados."""
    (tmp_path / "systemd").mkdir()
    for sha in versoes:
        unidades = tmp_path / "versoes" / sha / "vm" / "systemd"
        unidades.mkdir(parents=True)
        (tmp_path / "versoes" / sha / "compose.yml").write_text("services: {}\n")
        for unidade in deploy.UNIDADES_DO_BACKUP:
            (unidades / unidade).write_text(f"# {unidade} de {sha}\n")
    if no_ar is not None:
        (tmp_path / "tag-atual").write_text(no_ar + "\n")
    return tmp_path


def _implantar(sha: str, pasta: Path, maquina: Maquina, segredos: Mapping[str, str]) -> int:
    return deploy.implantar(
        sha,
        rodar=maquina,
        cofre=CofreFalso(segredos),
        pasta=pasta,
        systemd=pasta / "systemd",
        dormir=lambda _: None,
    )


# ─── o caminho feliz ──────────────────────────────────────────────────────────────────────


def test_deploy_segue_a_ordem_e_marca_a_versao(tmp_path: Path) -> None:
    pasta = _pasta(tmp_path, SHA_A)
    maquina = Maquina()

    codigo = _implantar(SHA_A, pasta, maquina, SEGREDOS)

    assert codigo == 0
    assert maquina.passos() == [
        ("ssh", None),
        ("baixar", SHA_A),
        ("banco", SHA_A),
        ("migrar", SHA_A),
        ("subir", SHA_A),
        ("saude", None),
        ("agendar", None),  # systemctl daemon-reload
        ("agendar", None),  # systemctl enable --now do agendamento do backup
        ("outro", None),  # a limpeza das imagens antigas
    ]
    assert (pasta / "tag-atual").read_text().strip() == SHA_A


def test_deploy_agenda_o_backup_com_os_arquivos_da_versao(tmp_path: Path) -> None:
    pasta = _pasta(tmp_path, SHA_A)
    maquina = Maquina()

    _implantar(SHA_A, pasta, maquina, SEGREDOS)

    for unidade in deploy.UNIDADES_DO_BACKUP:
        assert (pasta / "systemd" / unidade).read_text() == f"# {unidade} de {SHA_A}\n"
    comandos = [c for c, _ in maquina.comandos]
    assert ["systemctl", "enable", "--now", "verifyscan-backup.timer"] in comandos


def test_site_no_ar_sem_backup_agendado_nao_passa_por_sucesso(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """O site subiu, então a marca aponta para a versão nova; mas ficar sem backup em silêncio
    seria pior do que um deploy vermelho."""
    pasta = _pasta(tmp_path, SHA_A)
    maquina = Maquina(quebra=("agendar", SHA_A))

    codigo = _implantar(SHA_A, pasta, maquina, SEGREDOS)

    assert codigo != 0
    assert (pasta / "tag-atual").read_text().strip() == SHA_A
    saida = capsys.readouterr().out
    assert "DEPLOY_INCOMPLETO" in saida and "DEPLOY_OK" not in saida


def test_deploy_que_falha_nao_mexe_no_agendamento(tmp_path: Path) -> None:
    pasta = _pasta(tmp_path, SHA_A)
    maquina = Maquina(quebra=("saude", SHA_A))

    _implantar(SHA_A, pasta, maquina, SEGREDOS)

    assert list((pasta / "systemd").iterdir()) == []
    assert ("agendar", None) not in maquina.passos()


def test_compose_usa_os_arquivos_da_versao_e_o_ambiente_do_cofre(tmp_path: Path) -> None:
    pasta = _pasta(tmp_path, SHA_A)
    maquina = Maquina()

    _implantar(SHA_A, pasta, maquina, SEGREDOS)

    subir = next(c for c in maquina.do_docker() if "--remove-orphans" in c)
    assert str(pasta / "versoes" / SHA_A / "compose.yml") in subir
    assert str(pasta / config.ARQUIVO_DE_AMBIENTE) in subir


def test_a_saude_e_pedida_pelo_endereco_publico_na_propria_vm(tmp_path: Path) -> None:
    """Pelo Caddy, com o certificado de verdade: é a cadeia inteira, como o visitante a vê."""
    pasta = _pasta(tmp_path, SHA_A)
    maquina = Maquina()

    _implantar(SHA_A, pasta, maquina, SEGREDOS)

    saude = next(c for c, _ in maquina.comandos if c[0] == "curl")
    assert f"https://{config.DOMINIO}/health" in saude
    assert f"{config.DOMINIO}:443:127.0.0.1" in saude


def test_o_ssh_e_desligado_a_cada_deploy(tmp_path: Path) -> None:
    """Defesa em profundidade: a porta 22 já é fechada no NSG, e o serviço fica desligado e
    mascarado na VM. No deploy, para valer também numa VM recriada."""
    pasta = _pasta(tmp_path, SHA_A)
    maquina = Maquina()

    _implantar(SHA_A, pasta, maquina, SEGREDOS)

    assert maquina.comandos[0][0] == ["systemctl", "mask", "--now", "ssh.socket", "ssh.service"]


# ─── os segredos ──────────────────────────────────────────────────────────────────────────


def test_o_arquivo_de_ambiente_so_o_root_le_e_tem_o_que_o_compose_pede(tmp_path: Path) -> None:
    pasta = _pasta(tmp_path, SHA_A)

    _implantar(SHA_A, pasta, Maquina(), SEGREDOS)

    arquivo = pasta / config.ARQUIVO_DE_AMBIENTE
    linhas = arquivo.read_text().splitlines()
    assert f"POSTGRES_PASSWORD='senha-{MARCA}'" in linhas
    assert f"PROXY_SEGREDO='proxy-{MARCA}'" in linhas
    assert f"DOMINIO='{config.DOMINIO}'" in linhas
    # Opcional ausente do cofre: a variável vai vazia.
    assert "VIRUSTOTAL_API_KEY=''" in linhas
    # A versão não fica no arquivo: vai no ambiente de cada comando, para a volta poder trocá-la.
    assert not any(linha.startswith("TAG=") for linha in linhas)
    if os.name == "posix":  # o Windows não tem essas permissões
        assert stat.S_IMODE(arquivo.stat().st_mode) == 0o600


def test_segredo_nunca_vai_para_a_linha_de_comando_nem_para_a_saida(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pasta = _pasta(tmp_path, SHA_A)
    maquina = Maquina()

    _implantar(SHA_A, pasta, maquina, SEGREDOS)

    impresso = capsys.readouterr()
    assert MARCA not in impresso.out + impresso.err
    for comando, ambiente in maquina.comandos:
        assert MARCA not in " ".join(comando)
        assert MARCA not in " ".join(ambiente.values())


@pytest.mark.parametrize("valor", [None, "", "   ", config.A_PREENCHER])
def test_falta_segredo_obrigatorio_recusa_antes_do_docker(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], valor: str | None
) -> None:
    pasta = _pasta(tmp_path, SHA_A)
    maquina = Maquina()
    segredos = {k: v for k, v in SEGREDOS.items() if k != "PROXY-SEGREDO"}
    if valor is not None:
        segredos["PROXY-SEGREDO"] = valor

    codigo = _implantar(SHA_A, pasta, maquina, segredos)

    assert codigo != 0
    assert maquina.do_docker() == []
    saida = capsys.readouterr().out
    # Diz QUAL nome falta, para o Walter saber o que preencher.
    assert "PROXY-SEGREDO" in saida
    assert MARCA not in saida


@pytest.mark.parametrize("ruim", ["com'aspas", "duas\nlinhas"])
def test_valor_que_quebraria_o_arquivo_e_recusado_sem_ser_mostrado(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], ruim: str
) -> None:
    pasta = _pasta(tmp_path, SHA_A)
    maquina = Maquina()

    codigo = _implantar(SHA_A, pasta, maquina, {**SEGREDOS, "ANTHROPIC-API-KEY": MARCA + ruim})

    assert codigo != 0
    assert maquina.do_docker() == []
    saida = capsys.readouterr().out
    assert "ANTHROPIC-API-KEY" in saida
    assert MARCA not in saida


# ─── a versão pedida ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("sha", ["", "abc", "A" * 40, "a" * 39 + ";", "../" + "a" * 37])
def test_versao_que_nao_e_um_sha_inteiro_e_recusada_sem_rodar_nada(
    tmp_path: Path, sha: str
) -> None:
    maquina = Maquina()

    codigo = _implantar(sha, _pasta(tmp_path), maquina, SEGREDOS)

    assert codigo != 0
    assert maquina.comandos == []


def test_versao_sem_os_arquivos_baixados_e_recusada(tmp_path: Path) -> None:
    maquina = Maquina()

    codigo = _implantar(SHA_B, _pasta(tmp_path, SHA_A), maquina, SEGREDOS)

    assert codigo != 0
    assert maquina.do_docker() == []


# ─── a volta automática ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("passo", ["baixar", "migrar", "subir", "saude"])
def test_falhou_volta_sozinho_para_a_versao_anterior(tmp_path: Path, passo: str) -> None:
    pasta = _pasta(tmp_path, SHA_A, SHA_B, no_ar=SHA_A)
    maquina = Maquina(quebra=(passo, SHA_B))
    maquina.no_ar = SHA_A

    codigo = _implantar(SHA_B, pasta, maquina, SEGREDOS)

    assert codigo != 0
    # A anterior subiu de novo, com os arquivos dela, e respondeu.
    assert maquina.no_ar == SHA_A
    assert maquina.passos()[-2:] == [("subir", SHA_A), ("saude", None)]
    volta = maquina.do_docker()[-1]
    assert str(pasta / "versoes" / SHA_A / "compose.yml") in volta
    # A marca continua na versão que está de fato no ar.
    assert (pasta / "tag-atual").read_text().strip() == SHA_A


def test_a_volta_nao_desfaz_migracao(tmp_path: Path) -> None:
    """As migrações são aditivas (README): a versão anterior roda com o banco já migrado."""
    pasta = _pasta(tmp_path, SHA_A, SHA_B, no_ar=SHA_A)
    maquina = Maquina(quebra=("saude", SHA_B))
    maquina.no_ar = SHA_A

    _implantar(SHA_B, pasta, maquina, SEGREDOS)

    assert not any("downgrade" in c for c in maquina.do_docker())


def test_primeiro_deploy_que_falha_nao_tem_para_onde_voltar(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pasta = _pasta(tmp_path, SHA_A)
    maquina = Maquina(quebra=("saude", SHA_A))

    codigo = _implantar(SHA_A, pasta, maquina, SEGREDOS)

    assert codigo != 0
    assert not (pasta / "tag-atual").exists()
    assert maquina.passos().count(("subir", SHA_A)) == 1
    assert "DEPLOY_FALHOU" in capsys.readouterr().out


def test_a_saude_insiste_antes_de_desistir(tmp_path: Path) -> None:
    """No primeiro deploy o Caddy ainda pede o certificado: não pode desistir na 1ª tentativa."""
    pasta = _pasta(tmp_path, SHA_A)
    maquina = Maquina(quebra=("saude", SHA_A))

    _implantar(SHA_A, pasta, maquina, SEGREDOS)

    assert maquina.passos().count(("saude", None)) == deploy.TENTATIVAS_DE_SAUDE


def test_sucesso_guarda_a_anterior_e_apaga_as_mais_velhas(tmp_path: Path) -> None:
    velha = "c" * 40
    pasta = _pasta(tmp_path, velha, SHA_A, SHA_B, no_ar=SHA_A)
    (pasta / "tag-anterior").write_text(velha + "\n")
    maquina = Maquina()
    maquina.no_ar = SHA_A

    codigo = _implantar(SHA_B, pasta, maquina, SEGREDOS)

    assert codigo == 0
    assert (pasta / "tag-atual").read_text().strip() == SHA_B
    assert (pasta / "tag-anterior").read_text().strip() == SHA_A
    assert sorted(p.name for p in (pasta / "versoes").iterdir()) == [SHA_A, SHA_B]
