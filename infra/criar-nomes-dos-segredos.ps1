# Cria no cofre os NOMES dos segredos que o deploy lê, com o valor "PREENCHER" (ADR-0029).
# Os valores de verdade quem coloca é o Walter, pelo portal: este script nunca os vê.
#
# Pode rodar de novo à vontade: um segredo que já existe NÃO é tocado, com ou sem valor. Por isso
# os segredos ficam fora do main.bicep: reaplicar o Bicep sobrescreveria o que foi preenchido.
#
#   .\infra\criar-nomes-dos-segredos.ps1
#
# A lista tem de bater com infra/vm/config.py. Os quatro últimos são opcionais: deixados como
# "PREENCHER", o recurso fica desligado. O deploy recusa um obrigatório que ainda esteja assim.

$cofre = "kv-vscan-6of3ik2bfrhr4"
$nomes = @(
    "POSTGRES-PASSWORD",
    "IP-HMAC-SEGREDO",
    "PROXY-SEGREDO",
    "ANTHROPIC-API-KEY",
    "EMAIL-ACME",
    "SAFE-BROWSING-API-KEY",
    "VIRUSTOTAL-API-KEY",
    "METRICS-TOKEN",
    "SENTRY-DSN"
)

foreach ($nome in $nomes) {
    # Só o id, nunca o valor: a saída deste script não mostra segredo.
    # (As mensagens abaixo vão sem acento: o PowerShell 5.1 lê este arquivo como ANSI.)
    $existe = az keyvault secret show --vault-name $cofre --name $nome --query id -o tsv 2>$null
    if ($existe) {
        "{0,-24} ja existe: nao foi tocado" -f $nome
    }
    else {
        az keyvault secret set --vault-name $cofre --name $nome --value "PREENCHER" --query name -o tsv | Out-Null
        "{0,-24} criado, a preencher" -f $nome
    }
}
