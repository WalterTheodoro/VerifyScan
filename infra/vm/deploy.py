"""O deploy, dentro da VM (ADR-0029). Quem chama é o `entrar.sh`, pelo run-command:

    python3 -m vm.deploy <sha do commit>

Os passos, nesta ordem:

1. desliga o SSH da VM (o acesso é só por run-command);
2. lê os segredos do cofre, com a identidade da VM, e escreve o arquivo de ambiente do compose;
3. baixa as imagens da versão, sobe o banco, roda as migrações e sobe o resto;
4. pergunta ao próprio site, pelo endereço público, se ele está de pé (`/health`);
5. se qualquer coisa do passo 3 ou 4 falhar, VOLTA SOZINHO para a versão anterior.

A volta troca as imagens e os arquivos do compose; ela NÃO desfaz migração. Por isso toda
migração é aditiva (README): a versão anterior tem de rodar com o banco já migrado.

Nenhum segredo é impresso nem passado na linha de comando: eles vão do cofre para um arquivo
que só o root lê, e o compose os lê de lá.

Os comandos do sistema e o cofre entram por parâmetro: nos testes, são falsos (CLAUDE.md §6).
"""

import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

from vm import config
from vm.azure import Azure, ErroDoAzure

# (comando, variáveis de ambiente a mais) → nada; lança `CalledProcessError` se o comando falhar.
Rodar = Callable[[list[str], Mapping[str, str]], None]

# O SHA inteiro do commit, e só ele: é o que vira nome de pasta e tag de imagem.
_SHA = re.compile(r"[0-9a-f]{40}")
# No primeiro deploy o Caddy ainda pede o certificado: 30 tentativas a cada 5 s, até 2,5 min.
TENTATIVAS_DE_SAUDE = 30
ESPERA_ENTRE_TENTATIVAS_S = 5
# O agendamento do backup diário (infra/vm/systemd/), instalado a cada deploy.
UNIDADES_DO_BACKUP = ("verifyscan-backup.service", "verifyscan-backup.timer")


class LeitorDeSegredos(Protocol):
    def ler_segredo(self, cofre: str, nome: str) -> str | None: ...


class DeployRecusado(Exception):
    """O deploy nem começou: nada foi tocado. A mensagem diz o motivo, sem valor de segredo."""


class SiteNaoRespondeu(Exception):
    """O `/health` não respondeu 200 depois de todas as tentativas."""


def rodar_de_verdade(comando: list[str], ambiente: Mapping[str, str]) -> None:
    subprocess.run(comando, check=True, env={**os.environ, **ambiente})


def _dizer(texto: str) -> None:
    """A saída do run-command chega em bloco, no fim: `flush` mantém a ordem com a do Docker."""
    print(texto, flush=True)


# ─── segredos ─────────────────────────────────────────────────────────────────────────────


def ler_ambiente(cofre: LeitorDeSegredos) -> dict[str, str]:
    """As variáveis do compose, com os valores do cofre. Recusa se faltar algum obrigatório."""
    ambiente = {"DOMINIO": config.DOMINIO}
    faltando = []
    for nome, variavel in config.SEGREDOS_OBRIGATORIOS.items():
        valor = cofre.ler_segredo(config.COFRE, nome)
        if valor is None or not valor.strip() or valor == config.A_PREENCHER:
            faltando.append(nome)
        else:
            ambiente[variavel] = valor
    if faltando:
        raise DeployRecusado(f"Faltam no cofre, ou estão sem valor: {', '.join(faltando)}.")
    for nome, variavel in config.SEGREDOS_OPCIONAIS.items():
        valor = cofre.ler_segredo(config.COFRE, nome)
        ambiente[variavel] = "" if valor is None or valor == config.A_PREENCHER else valor
    # O arquivo guarda cada valor entre aspas simples, numa linha: o que o compose lê ao pé da
    # letra. Um valor com aspas simples ou quebra de linha quebraria o arquivo.
    nomes = {**config.SEGREDOS_OBRIGATORIOS, **config.SEGREDOS_OPCIONAIS}
    for nome, variavel in nomes.items():
        if "'" in ambiente[variavel] or "\n" in ambiente[variavel]:
            raise DeployRecusado(f"O valor de {nome} tem aspas simples ou quebra de linha.")
    return ambiente


def escrever_ambiente(caminho: Path, ambiente: Mapping[str, str]) -> None:
    """Criado já com permissão só do root (0600): o arquivo nunca existe legível por outros."""
    descritor = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descritor, "w", encoding="utf-8") as arquivo:
        for variavel, valor in ambiente.items():
            arquivo.write(f"{variavel}='{valor}'\n")
    os.chmod(caminho, 0o600)


# ─── os passos ────────────────────────────────────────────────────────────────────────────


def _compose(rodar: Rodar, pasta: Path, sha: str, *argumentos: str) -> None:
    """`docker compose` com os arquivos DAQUELA versão. A tag vai no ambiente do comando, e não
    no arquivo de ambiente: é o que deixa a volta usar outra versão com os mesmos segredos."""
    rodar(
        [
            "docker",
            "compose",
            "--progress",
            "quiet",
            "--env-file",
            str(pasta / config.ARQUIVO_DE_AMBIENTE),
            "-f",
            str(pasta / "versoes" / sha / "compose.yml"),
            *argumentos,
        ],
        {"TAG": sha},
    )


def _esperar_o_site(rodar: Rodar, dormir: Callable[[float], None]) -> None:
    """Pelo endereço público, resolvido para a própria VM: passa pelo Caddy, com o certificado
    de verdade, pelo frontend e pelo backend, que faz `SELECT 1` no banco."""
    comando = [
        "curl",
        "--fail",
        "--silent",
        "--output",
        "/dev/null",
        "--max-time",
        "10",
        "--resolve",
        f"{config.DOMINIO}:443:127.0.0.1",
        f"https://{config.DOMINIO}/health",
    ]
    for tentativa in range(1, TENTATIVAS_DE_SAUDE + 1):
        try:
            rodar(comando, {})
            return
        except subprocess.CalledProcessError:
            if tentativa < TENTATIVAS_DE_SAUDE:
                dormir(ESPERA_ENTRE_TENTATIVAS_S)
    raise SiteNaoRespondeu()


def _subir(rodar: Rodar, pasta: Path, sha: str, dormir: Callable[[float], None]) -> None:
    _dizer(f"Baixando as imagens de {sha}.")
    _compose(rodar, pasta, sha, "pull")
    _dizer("Subindo o banco e rodando as migrações.")
    _compose(rodar, pasta, sha, "up", "-d", "--wait", "postgres")
    _compose(rodar, pasta, sha, "run", "--rm", "backend", "alembic", "upgrade", "head")
    _dizer("Subindo o site.")
    _compose(rodar, pasta, sha, "up", "-d", "--wait", "--remove-orphans")
    _dizer("Conferindo o /health pelo endereço público.")
    _esperar_o_site(rodar, dormir)


def _voltar(rodar: Rodar, pasta: Path, anterior: str, dormir: Callable[[float], None]) -> None:
    """Só sobe: as imagens da anterior já estão na VM, e o banco fica como está."""
    _compose(rodar, pasta, anterior, "up", "-d", "--wait", "--remove-orphans")
    _esperar_o_site(rodar, dormir)


def _ler_marca(caminho: Path) -> str | None:
    if not caminho.exists():
        return None
    valor = caminho.read_text(encoding="utf-8").strip()
    return valor if _SHA.fullmatch(valor) else None


def _agendar_backup(rodar: Rodar, pasta: Path, sha: str, systemd: Path) -> None:
    """Copia os dois arquivos do agendamento para o systemd e liga o temporizador. A cada
    deploy, e não só no cloud-init: assim uma mudança no horário chega à VM como qualquer outra."""
    for unidade in UNIDADES_DO_BACKUP:
        shutil.copyfile(pasta / "versoes" / sha / "vm" / "systemd" / unidade, systemd / unidade)
    rodar(["systemctl", "daemon-reload"], {})
    rodar(["systemctl", "enable", "--now", "verifyscan-backup.timer"], {})


def _limpar(rodar: Rodar, pasta: Path, manter: set[str]) -> None:
    """Fora a versão no ar e a anterior, apaga os arquivos das outras e as imagens sem uso há
    mais de uma semana. Falhar aqui não desfaz um deploy que deu certo."""
    for versao in (pasta / "versoes").iterdir():
        if _SHA.fullmatch(versao.name) and versao.name not in manter:
            shutil.rmtree(versao, ignore_errors=True)
    try:
        rodar(["docker", "image", "prune", "--all", "--force", "--filter", "until=168h"], {})
    except subprocess.CalledProcessError:
        _dizer("Aviso: não deu para apagar as imagens antigas.")


# ─── o deploy ─────────────────────────────────────────────────────────────────────────────


def implantar(
    sha: str,
    *,
    rodar: Rodar,
    cofre: LeitorDeSegredos,
    pasta: Path,
    systemd: Path = Path("/etc/systemd/system"),
    dormir: Callable[[float], None] = time.sleep,
) -> int:
    """Devolve 0 se a versão pedida ficou no ar, com o backup agendado; outro número se não."""
    if not _SHA.fullmatch(sha):
        _dizer("DEPLOY_RECUSADO: a versão tem de ser o SHA inteiro do commit.")
        return 2
    if not (pasta / "versoes" / sha / "compose.yml").is_file():
        _dizer(f"DEPLOY_RECUSADO: os arquivos da versão {sha} não estão na VM.")
        return 2

    # Defesa em profundidade: a porta 22 já é fechada no NSG. Mascarado, o serviço não volta
    # nem numa atualização do pacote. Aqui, e não só no cloud-init: vale para uma VM recriada.
    try:
        rodar(["systemctl", "mask", "--now", "ssh.socket", "ssh.service"], {})
    except subprocess.CalledProcessError:
        _dizer("DEPLOY_RECUSADO: não deu para desligar o SSH da VM.")
        return 2

    try:
        escrever_ambiente(pasta / config.ARQUIVO_DE_AMBIENTE, ler_ambiente(cofre))
    except (DeployRecusado, ErroDoAzure) as erro:
        _dizer(f"DEPLOY_RECUSADO: {erro}")
        return 2

    anterior = _ler_marca(pasta / "tag-atual")
    try:
        _subir(rodar, pasta, sha, dormir)
    except (subprocess.CalledProcessError, SiteNaoRespondeu) as erro:
        motivo = "o site não respondeu" if isinstance(erro, SiteNaoRespondeu) else "um passo falhou"
        if anterior is None or anterior == sha:
            _dizer(f"DEPLOY_FALHOU: {motivo}, e não há versão anterior para voltar.")
            return 1
        _dizer(f"A versão {sha} falhou ({motivo}). Voltando para {anterior}.")
        try:
            _voltar(rodar, pasta, anterior, dormir)
        except (subprocess.CalledProcessError, SiteNaoRespondeu):
            _dizer(f"DEPLOY_FALHOU: e a volta para {anterior} também falhou. O site está fora.")
            return 3
        _dizer(f"DEPLOY_FALHOU: o site voltou para {anterior} e está respondendo.")
        return 1

    # Só agora a versão nova vira "a atual": a marca nunca aponta para algo que não respondeu.
    if anterior is not None and anterior != sha:
        (pasta / "tag-anterior").write_text(anterior + "\n", encoding="utf-8")
    (pasta / "tag-atual").write_text(sha + "\n", encoding="utf-8")
    try:
        _agendar_backup(rodar, pasta, sha, systemd)
    except (OSError, subprocess.CalledProcessError):
        # O site está no ar, mas sem backup agendado: melhor um deploy vermelho do que ficar
        # sem cópia em silêncio.
        _dizer(f"DEPLOY_INCOMPLETO: {sha} está no ar, mas o backup diário NÃO ficou agendado.")
        return 4
    _limpar(rodar, pasta, {sha, anterior or sha})
    _dizer(f"DEPLOY_OK: {sha} está no ar.")
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        _dizer("uso: python3 -m vm.deploy <sha do commit>")
        return 2
    # Importado aqui: o `fcntl` só existe no Linux, e os testes também rodam no Windows.
    import fcntl

    # Um deploy por vez na VM, mesmo que dois run-commands cheguem juntos. O workflow já impede
    # isso com `concurrency`; esta trava é a segunda barreira.
    with open(config.PASTA / "deploy.trava", "w", encoding="utf-8") as trava:
        try:
            fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            _dizer("DEPLOY_RECUSADO: já há um deploy em andamento na VM.")
            return 2
        return implantar(sys.argv[1], rodar=rodar_de_verdade, cofre=Azure(), pasta=config.PASTA)


if __name__ == "__main__":
    sys.exit(main())
