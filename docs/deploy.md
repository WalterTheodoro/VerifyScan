# Deploy e operação da produção

Como a produção na Azure é publicada, conferida e consertada. As decisões e os porquês estão no
[ADR-0029](adr/ADR-0029-hospedagem-na-azure.md).

> **Estado em 26/11/2026:** a infraestrutura está criada, mas a produção ainda responde pelo
> Render. O endereço abaixo passa a ser o oficial no [corte](#o-corte).

| O quê | Onde |
|---|---|
| Endereço | <https://verifyscan.chilecentral.cloudapp.azure.com> |
| Grupo de recursos | `rg-verifyscan`, região `chilecentral` |
| VM | `vm-verifyscan` (Ubuntu 24.04, sem SSH) |
| Cofre de segredos | `kv-vscan-6of3ik2bfrhr4` |
| Backups | conta `stvscan6of3ik2bfrhr4`, container `backups` |
| Imagens | `ghcr.io/waltertheodoro/verifyscan-backend` e `-frontend`, tag = SHA do commit |

## Como um deploy acontece

Sozinho. Todo push na `master` roda o CI; se ele termina verde, o workflow **Deploy** começa:

1. constrói as duas imagens e as publica com o SHA do commit;
2. entra na Azure (sem senha: token do GitHub) e manda a VM publicar aquele SHA;
3. a VM lê os segredos do cofre, baixa as imagens, roda as migrações e sobe tudo;
4. a VM confere o `/health`. Se não responder, volta para a versão anterior;
5. o workflow confere o `/health` de fora.

Acompanhe em **Actions → Deploy**. A última linha do passo "Deploy na VM" diz o que aconteceu:

| Linha | O que quer dizer | O que fazer |
|---|---|---|
| `DEPLOY_OK` | a versão nova está no ar | nada |
| `DEPLOY_RECUSADO` | nem começou; nada foi tocado | a linha diz o motivo (em geral, segredo faltando no cofre) |
| `DEPLOY_FALHOU: o site voltou para …` | a nova não respondeu; a anterior está no ar | ver os [logs](#ver-os-logs), corrigir e mandar de novo |
| `DEPLOY_FALHOU: … não há versão anterior` | falhou no primeiro deploy | ver os logs; o site está fora |
| `DEPLOY_FALHOU: e a volta … também falhou` | o site está fora | ver os logs; restaurar o backup, se for o banco |
| `DEPLOY_INCOMPLETO` | o site está no ar, mas o backup diário não ficou agendado | rodar o deploy de novo |

**Toda migração tem de ser aditiva.** A volta troca as imagens, mas não desfaz migração: a versão
anterior precisa rodar com o banco já migrado. Remover ou renomear coluna leva dois deploys.

Cada deploy derruba o site por alguns segundos, enquanto os contêineres trocam.

## Voltar uma versão

**Actions → Deploy → Run workflow**, na `master`, com o SHA **inteiro** (40 caracteres) do commit
para o qual se quer voltar. Tem de ser um commit da `master`. As imagens dele já estão
publicadas; o workflow só manda a VM subi-las.

O banco não volta junto. Se o problema é o dado, e não o código, veja
[Restaurar um backup](#restaurar-um-backup).

## Comandos na VM, sem SSH

A VM não tem SSH. Tudo passa pelo *run-command* da Azure, que manda o `infra/vm/entrar.sh` com
dois argumentos: o SHA de um commit da `master` e a ação.

No PowerShell, **na raiz do repositório**, com `az login` feito:

```powershell
git fetch origin
$sha = git rev-parse origin/master

function Na-VM {
    $r = az vm run-command invoke --resource-group rg-verifyscan --name vm-verifyscan `
        --command-id RunShellScript --scripts "@infra/vm/entrar.sh" `
        --parameters $sha @args -o json | Out-String | ConvertFrom-Json
    $r.value[0].message
}
```

Depois disso, cada ação é uma linha:

| Comando | O que faz |
|---|---|
| `Na-VM logs backend` | as últimas linhas do log de um serviço |
| `Na-VM backup` | faz um backup agora |
| `Na-VM restaurar` | restaura o backup mais recente (**apaga o banco atual**) |
| `Na-VM migrar_neon` | copia os dados do Neon para a VM |
| `Na-VM alerta` | manda um evento de teste ao Sentry |
| `Na-VM deploy` | publica o commit de `$sha` (o normal é o workflow fazer isso) |

Três coisas a saber:

- **O `az` responde "Enable succeeded" mesmo quando a ação falha.** Leia a saída: cada ação
  termina com uma palavra (`BACKUP_OK`, `MIGRACAO_FALHOU`, …).
- **Só chegam os últimos 4 KB da saída**, e só um comando roda por vez na VM. Durante um deploy,
  os outros esperam ou são recusados.
- **Para alterar qualquer coisa na Azure, o login precisa de dois fatores.** Se o `az` recusar
  com `AADSTS50076`, ele mesmo mostra o comando de login a repetir.

No PowerShell do Windows os acentos da saída podem aparecer trocados. As palavras que dizem o
resultado não têm acento, de propósito.

## Ver os logs

```powershell
Na-VM logs backend                    # ou: frontend, caddy, postgres
Na-VM logs backend 22d60208-6f7f      # só as linhas com esse texto
Na-VM logs backup                     # o que o backup diário escreveu
```

Saem as linhas mais recentes que cabem em 4 KB (umas 10 a 15 do backend). Para ir atrás de uma
requisição, use o `X-Request-ID` dela como filtro
([observabilidade](observabilidade.md#seguir-uma-requisição)).

Os logs levam só metadado. O do Caddy não tem log de acesso, e a linha de erro sai sem o pedido.

## Backup

Todo dia às 03:00 de Brasília (06:00 UTC), a VM grava uma cópia do banco no armazenamento da
Azure e apaga as cópias com 7 dias ou mais. A cópia nunca vira arquivo na VM.

- **Conferir que rodou:** `Na-VM logs backup`. A linha boa é `BACKUP_OK: verifyscan-AAAAMMDDTHHMMSSZ.dump, …`.
- **Fazer um agora:** `Na-VM backup` (antes de uma mudança arriscada, por exemplo).
- **Listar as cópias:** `Na-VM restaurar listar`. Não existe backup com esse nome: a ação recusa,
  sem tocar em nada, e mostra os que existem.
- **Se falhar:** chega um e-mail do Sentry, projeto do backend, com "O backup do banco falhou" e
  o motivo. Falhas repetidas com o mesmo motivo ficam na mesma ocorrência: marque-a como
  resolvida depois de consertar, para a próxima avisar de novo.
- **Conferir que o aviso funciona:** `Na-VM alerta`, e esperar o e-mail "Teste do aviso da VM".

### Restaurar um backup

**Apaga o que está no banco** e põe no lugar o que estava na cópia. Tudo o que foi gravado depois
dela se perde.

```powershell
Na-VM restaurar                                    # o mais recente
Na-VM restaurar verifyscan-20261210T060000Z.dump   # um específico
```

O site fica parado durante a restauração e volta sozinho no fim, mesmo se ela falhar. Ela roda
numa transação só: se falhar no meio, o banco fica como estava. Termina com `RESTAURACAO_OK`,
`RESTAURACAO_RECUSADA` (nome que não existe) ou `RESTAURACAO_FALHOU`.

A cópia tem de ser de uma versão do banco igual ou anterior à do código no ar. Se o código voltou
para antes de uma migração, restaure e faça o deploy da versão certa em seguida.

## Segredos

Ficam no cofre, e a VM os lê a cada deploy. **Trocar um valor só vale depois de um novo deploy**
(Actions → Deploy → Run workflow com o SHA que está no ar).

No portal: o cofre → **Objetos → Segredos** → o segredo → **+ Nova versão**.

| Nome no cofre | De onde vem | Obrigatório |
|---|---|---|
| `POSTGRES-PASSWORD` | gerada uma vez, só com letras, números, `-` e `_`. **Só vale na primeira subida do banco:** trocar depois quebra a conexão | sim |
| `IP-HMAC-SEGREDO` | o mesmo valor do Render. **Não trocar:** zera as cotas do dia | sim |
| `PROXY-SEGREDO` | gerado uma vez | sim |
| `ANTHROPIC-API-KEY` | console da Anthropic | sim |
| `EMAIL-ACME` | um e-mail seu, para o emissor do certificado | sim |
| `SENTRY-DSN` | Sentry, projeto do backend | não |
| `METRICS-TOKEN` | gerado uma vez | não |
| `SAFE-BROWSING-API-KEY` | Google Cloud | não |
| `VIRUSTOTAL-API-KEY` | VirusTotal | não |

Um opcional ausente, ou ainda com o valor `PREENCHER`, deixa o recurso desligado. Um obrigatório
assim faz o deploy ser recusado. Nenhum valor pode ter aspas simples nem quebra de linha.

O que o **frontend** recebe no build são variáveis do repositório no GitHub (Settings → Secrets
and variables → Actions → Variables), públicas por definição: `NEXT_PUBLIC_SENTRY_DSN`,
`NEXT_PUBLIC_SENTRY_ENVIRONMENT`, `NEXT_PUBLIC_CONTATO_PRIVACIDADE` e, para os source maps,
`SENTRY_ORG`, `SENTRY_PROJECT` e o segredo `SENTRY_AUTH_TOKEN`. Mudou uma delas: a imagem só muda
no próximo commit.

## Migrar os dados do Neon

Duas rodadas: uma para validar o site novo com dados de verdade, e outra logo antes do corte.
Cada rodada **substitui** o que está no banco da VM.

1. No portal, no cofre: **+ Gerar/Importar**, nome `NEON-DATABASE-URL`, valor = a string
   **direta** do Neon (host sem `-pooler`).
2. `Na-VM migrar_neon`
3. Ler a tabela que ela mostra: uma linha por tabela, com a contagem na origem e no destino, e a
   versão do Alembic. Tem de terminar com `MIGRACAO_OK`.
4. Depois da última rodada, apagar o segredo `NEON-DATABASE-URL` do cofre.

O site da VM fica parado durante a cópia. Se a contagem do Neon mudar no meio (alguém usou o site
do Render naquele instante), a migração reprova e é só rodar de novo. A string do Neon não
aparece na saída nem em mensagem de erro.

O código no ar na VM tem de estar na mesma versão do Alembic do Neon: faça a migração logo depois
de um deploy da `master`, com o Render publicado no mesmo commit.

## A infraestrutura (Bicep)

Tudo o que existe na Azure está em `infra/main.bicep`, menos os valores dos segredos. Para mudar
um recurso, mude o arquivo e reaplique:

```powershell
$env:ID_DO_OPERADOR = az ad signed-in-user show --query id -o tsv

# O que vai mudar, sem mudar nada:
az deployment group what-if --resource-group rg-verifyscan `
    --template-file infra/main.bicep --parameters infra/producao.bicepparam

# Aplicar:
az deployment group create --resource-group rg-verifyscan `
    --template-file infra/main.bicep --parameters infra/producao.bicepparam
```

- **Baixar o tamanho da VM** (depois do Demo Day): em `infra/producao.bicepparam`, trocar
  `tamanhoDaVm` para `Standard_B2ats_v2` e reaplicar. A VM reinicia; uns 2 minutos fora.
- **O `cloud-init.yaml` só roda na criação da VM.** Mudá-lo não muda uma VM que já existe.
- **A chave SSH pública do `producao.bicepparam` não pode mudar.** A parte privada foi apagada de
  propósito; a pública só está lá porque a Azure exige.
- **Nomes dos segredos:** `infra/criar-nomes-dos-segredos.ps1` cria os que faltam, com o valor
  `PREENCHER`, e nunca sobrescreve.
- **Orçamento** (`infra/orcamento.bicep`): R$ 538, com aviso por e-mail em 60% e 85%. Como não é
  certo que o aviso dispare nesta assinatura, confira o saldo no portal nas datas do ADR-0029.

## O primeiro deploy

1. Cofre preenchido e ambiente `producao` criado no GitHub, com os três `AZURE_*`.
2. Merge do PR na `master`. O CI roda e o Deploy começa sozinho.
3. **O Deploy vai falhar na primeira vez:** o GitHub cria os pacotes das imagens como privados, e
   a VM não consegue baixá-los. No seu perfil → **Packages** → `verifyscan-backend` → **Package
   settings** → **Change visibility** → **Public**. Repetir para `verifyscan-frontend`.
4. Na execução que falhou: **Re-run failed jobs**.
5. Conferir: `DEPLOY_OK`, o endereço abre com o cadeado, e `Na-VM logs backup` no dia seguinte.

## O corte

O Render fica no ar até a VM estar validada. Nesta ordem:

1. **Rodada de validação:** `Na-VM migrar_neon`, e o teste do site novo:
   - texto, link e print, com e sem conta;
   - criar conta, entrar, ver o histórico, apagar uma análise, sair;
   - o cookie se chama `__Host-vs_sessao` (ferramentas do navegador → Aplicativo → Cookies);
   - a cota de quem não tem conta, de **dois IPs diferentes** (Wi-Fi e 4G): cada um tem a sua, e
     o "Restam N" de um não muda com o uso do outro;
   - a página `/privacidade` fala da Azure, no Chile.
2. **Rodada do corte:** `Na-VM migrar_neon` de novo, e conferir as contagens.
3. Trocar o endereço no README e nos documentos, e divulgar o novo.
4. Apagar o segredo `NEON-DATABASE-URL`.
5. Suspender os serviços no Render (o Walter) e, depois de alguns dias sem precisar voltar, o
   projeto no Neon.

Quem estava logado no Render precisa entrar de novo no endereço novo. O que for gravado no Render
entre a rodada do corte e a suspensão não vai para a VM: faça os passos 2 a 5 em seguida.

Depois do corte sai do código o que era só do Render (lista no fim do ADR-0029).

## Problemas comuns

**`DEPLOY_RECUSADO: Faltam no cofre, ou estão sem valor: …`**
Um segredo obrigatório não existe ou está como `PREENCHER`. Preencha e rode o Deploy de novo.

**O passo "Entrar no Azure" falha.**
Confira os três segredos do ambiente `producao` e se o job rodou a partir da `master`: a Azure só
aceita o token desse ambiente.

**O Deploy falha em "Baixando as imagens".**
Os pacotes do GitHub estão privados (passo 3 do primeiro deploy).

**O site não responde logo depois do primeiro deploy.**
O Caddy ainda está pedindo o certificado; o deploy espera até 2,5 minutos. Se passar disso,
`Na-VM logs caddy` mostra o que o emissor respondeu.

**O run-command responde `Conflict`.**
Já há um comando rodando na VM (um deploy, por exemplo). Espere terminar.

**O site caiu de madrugada por um minuto.**
É o reinício das atualizações de segurança, às 04:30 de Brasília, quando uma delas pede.
