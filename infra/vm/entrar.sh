#!/usr/bin/env bash
#
# A porta de entrada do run-command na VM (ADR-0029). O GitHub Actions (ou o Walter, pelo `az`)
# manda este arquivo com dois argumentos:
#
#   entrar.sh <sha do commit> <ação>
#
# Ele traz para a VM os arquivos de infra/ DAQUELE commit (compose.yml, Caddyfile e a pasta vm/)
# e entrega a ação ao Python. Nada aqui lê ou imprime segredo.
#
# Os arquivos vêm do próprio repositório no GitHub, que é público, pelo SHA inteiro: o conteúdo
# de um SHA não muda, então a VM roda exatamente o que passou no CI.

set -euo pipefail

sha="${1:-}"
acao="${2:-}"
repositorio="WalterTheodoro/VerifyScan"
pasta="/opt/verifyscan"

# O SHA vira nome de pasta e pedaço de URL: só 40 caracteres hexadecimais passam.
if [[ ! "$sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "RECUSADO: o primeiro argumento tem de ser o SHA inteiro do commit."
  exit 2
fi

# Só as ações que existem. Cada uma é um módulo de infra/vm/, com o mesmo nome.
case "$acao" in
  deploy | backup | restaurar | migrar_neon | alerta | logs) ;;
  *)
    echo "RECUSADO: ação desconhecida."
    exit 2
    ;;
esac

destino="$pasta/versoes/$sha"
if [[ ! -f "$destino/compose.yml" ]]; then
  mkdir -p "$pasta/versoes"
  # Baixa numa pasta provisória e só então move: um download pela metade nunca fica com o nome
  # de uma versão.
  provisoria="$(mktemp -d "$pasta/baixando.XXXXXX")"
  trap 'rm -rf "$provisoria"' EXIT
  curl --fail --silent --show-error --location --retry 3 \
    "https://codeload.github.com/$repositorio/tar.gz/$sha" \
    | tar --extract --gzip --directory "$provisoria" --strip-components=2 "VerifyScan-$sha/infra"
  mv "$provisoria" "$destino"
  trap - EXIT
fi

cd "$destino"
# O que vier depois da ação segue para o módulo (o backup a restaurar; o alvo e o filtro dos logs).
exec python3 -m "vm.$acao" "$sha" "${@:3}"
