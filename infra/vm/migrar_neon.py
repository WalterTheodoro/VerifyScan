"""A migração dos dados: do Neon para o Postgres da VM (ADR-0029). Só a pedido, pelo
run-command, depois do primeiro deploy:

    python3 -m vm.migrar_neon

A string de conexão do Neon vem de um segredo TEMPORÁRIO do cofre (`NEON-DATABASE-URL`), que o
Walter cria antes e apaga depois. Ela não aparece em lugar nenhum: nem na linha de comando (vai
no ambiente do processo, e o Docker a repassa ao contêiner pelo nome), nem na saída (uma
mensagem de erro do Postgres é mostrada sem o host, o usuário, a senha e o banco).

O que ela faz:

1. conta as linhas de cada tabela na origem;
2. para o site da VM (ninguém grava no destino durante a cópia);
3. copia: `pg_dump` da origem direto para o `pg_restore` do destino, numa transação só. O
   destino fica idêntico à origem, inclusive a versão do alembic;
4. conta de novo na origem e conta no destino;
5. religa o site e compara. Só passa se a origem não mudou durante a cópia e se o destino tem
   exatamente as mesmas contagens e a mesma versão do alembic.

Pode rodar mais de uma vez: cada rodada substitui o que está no destino. São duas rodadas, a de
validação e a do corte.
"""

import re
import sys
from collections.abc import Mapping
from typing import Protocol
from urllib.parse import unquote, urlsplit

from vm import config, contagem
from vm.azure import Azure, ErroDoAzure
from vm.sistema import REDE, SITE, ComandoFalhou, Executar, dizer, executar_de_verdade

SEGREDO_DA_ORIGEM = "NEON-DATABASE-URL"
SEGREDO_DO_DESTINO = "POSTGRES-PASSWORD"
# A mesma imagem do banco da VM: traz o pg_dump, o pg_restore e o psql da versão 16.
IMAGEM = "postgres:16-alpine"
# Sem senha na URL: ela vai na variável PGPASSWORD, só para o comando que fala com o destino.
DESTINO = "postgresql://verifyscan@postgres:5432/verifyscan"

# Só o esquema `public` (as nossas tabelas): extensões e papéis próprios do Neon ficam de fora.
_COPIAR = (
    "set -o pipefail; "
    'pg_dump --format=custom --schema=public --no-owner --no-privileges "$ORIGEM" '
    '| PGPASSWORD="$SENHA_DO_DESTINO" pg_restore --clean --if-exists --no-owner '
    f'--no-privileges --single-transaction --dbname="{DESTINO}"'
)
_IPV4 = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")


class LeitorDeSegredos(Protocol):
    def ler_segredo(self, cofre: str, nome: str) -> str | None: ...


def _no_conteiner(roteiro: str, *variaveis: str) -> list[str]:
    """Um contêiner avulso na rede do compose. `-e NOME`, sem valor: o Docker pega o valor do
    ambiente de quem o chamou, e ele não aparece na linha de comando."""
    repassar = [parte for variavel in variaveis for parte in ("-e", variavel)]
    return [
        "docker",
        "run",
        "--rm",
        "-i",
        "--network",
        REDE,
        *repassar,
        IMAGEM,
        "sh",
        "-c",
        roteiro,
    ]


def sem_dados_da_origem(texto: str, url: str) -> str:
    """A mensagem de erro do Postgres, sem nada que identifique a origem: a URL inteira, o
    host, o usuário, a senha, o banco e qualquer endereço IP."""
    partes = urlsplit(url)
    segredos = {url, partes.hostname, partes.username, partes.password, partes.path.lstrip("/")}
    segredos |= {unquote(s) for s in segredos if s}
    # Os maiores primeiro: um pedaço menor não pode estragar a troca de um maior que o contém.
    # Sem diferenciar maiúsculas de minúsculas: o Python devolve o host sempre em minúsculas.
    for segredo in sorted((s for s in segredos if s), key=len, reverse=True):
        texto = re.sub(re.escape(segredo), "[oculto]", texto, flags=re.IGNORECASE)
    return _IPV4.sub("[oculto]", texto)


def _mostrar(origem: Mapping[str, str], destino: Mapping[str, str]) -> bool:
    iguais = True
    dizer(f"{'tabela':<28}{'origem':>10}{'destino':>10}")
    for nome in sorted(set(origem) | set(destino)):
        na_origem, no_destino = origem.get(nome, "-"), destino.get(nome, "-")
        confere = na_origem == no_destino
        iguais = iguais and confere
        dizer(f"{nome:<28}{na_origem:>10}{no_destino:>10}{'' if confere else '   DIFERENTE'}")
    return iguais


def migrar(*, executar: Executar, cofre: LeitorDeSegredos) -> int:
    try:
        origem = cofre.ler_segredo(config.COFRE, SEGREDO_DA_ORIGEM)
        senha = cofre.ler_segredo(config.COFRE, SEGREDO_DO_DESTINO)
    except ErroDoAzure as erro:
        dizer(f"MIGRACAO_RECUSADA: {erro}")
        return 2
    for nome, valor in ((SEGREDO_DA_ORIGEM, origem), (SEGREDO_DO_DESTINO, senha)):
        if valor is None or not valor.strip() or valor == config.A_PREENCHER:
            dizer(f"MIGRACAO_RECUSADA: falta o segredo {nome} no cofre.")
            return 2
    assert origem is not None and senha is not None
    origem = origem.strip()
    ambiente = {"ORIGEM": origem, "SENHA_DO_DESTINO": senha, "PGPASSWORD": senha}

    def contar_na_origem() -> dict[str, str]:
        comando = _no_conteiner(f'{contagem.PSQL} "$ORIGEM"', "ORIGEM")
        return contagem.ler(executar(comando, ambiente, contagem.CONSULTA.encode()))

    try:
        antes = contar_na_origem()
    except ComandoFalhou as erro:
        dizer("MIGRACAO_FALHOU: não deu para ler a origem. O site não foi parado.")
        dizer(sem_dados_da_origem(erro.erro.strip(), origem))
        return 1

    dizer("Parando o site da VM para a cópia.")
    executar(["docker", "stop", *SITE], {}, None)
    try:
        executar(_no_conteiner(_COPIAR, "ORIGEM", "SENHA_DO_DESTINO"), ambiente, None)
        depois = contar_na_origem()
        comando = _no_conteiner(f'{contagem.PSQL} "{DESTINO}"', "PGPASSWORD")
        destino = contagem.ler(executar(comando, ambiente, contagem.CONSULTA.encode()))
    except ComandoFalhou as erro:
        dizer("MIGRACAO_FALHOU: a cópia não terminou. O destino ficou como estava.")
        dizer(sem_dados_da_origem(erro.erro.strip(), origem))
        return 1
    finally:
        executar(["docker", "start", *SITE], {}, None)

    iguais = _mostrar(depois, destino)
    if antes != depois:
        dizer("MIGRACAO_FALHOU: a origem mudou durante a cópia. Rode de novo.")
        return 1
    if not iguais:
        dizer("MIGRACAO_FALHOU: o destino não tem as mesmas contagens da origem.")
        return 1
    dizer(f"MIGRACAO_OK: {len(destino) - 1} tabelas iguais; alembic em {destino.get('alembic')}.")
    return 0


def main() -> int:
    return migrar(executar=executar_de_verdade, cofre=Azure())


if __name__ == "__main__":
    sys.exit(main())
