"""Nomes e endereços da produção (ADR-0029). Nada aqui é segredo: são os nomes dos recursos que
o `infra/main.bicep` criou, e os NOMES dos segredos. Os valores só existem no cofre."""

from pathlib import Path

DOMINIO = "verifyscan.chilecentral.cloudapp.azure.com"
COFRE = "kv-vscan-6of3ik2bfrhr4"
CONTA_DE_ARMAZENAMENTO = "stvscan6of3ik2bfrhr4"
CONTAINER_DE_BACKUPS = "backups"

# A pasta do deploy na VM, criada pelo cloud-init: só o root lê.
PASTA = Path("/opt/verifyscan")
# O arquivo que o compose lê com `--env-file`. Escrito a cada deploy, a partir do cofre.
ARQUIVO_DE_AMBIENTE = "producao.env"

# Nome do segredo no cofre → variável que o compose.yml espera. O cofre não aceita "_" em nome
# de segredo, por isso o hífen.
SEGREDOS_OBRIGATORIOS = {
    "POSTGRES-PASSWORD": "POSTGRES_PASSWORD",
    "IP-HMAC-SEGREDO": "IP_HMAC_SEGREDO",
    "PROXY-SEGREDO": "PROXY_SEGREDO",
    "ANTHROPIC-API-KEY": "ANTHROPIC_API_KEY",
    "EMAIL-ACME": "EMAIL_ACME",
}
# Ausentes do cofre, a variável vai vazia e o recurso fica desligado (o compose.yml explica).
SEGREDOS_OPCIONAIS = {
    "SAFE-BROWSING-API-KEY": "SAFE_BROWSING_API_KEY",
    "VIRUSTOTAL-API-KEY": "VIRUSTOTAL_API_KEY",
    "METRICS-TOKEN": "METRICS_TOKEN",
    "SENTRY-DSN": "SENTRY_DSN",
}
# O valor com que os nomes são criados no cofre, antes de o Walter preencher. O deploy recusa
# um segredo obrigatório que ainda esteja assim.
A_PREENCHER = "PREENCHER"
