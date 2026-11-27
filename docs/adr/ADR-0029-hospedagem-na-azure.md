# ADR-0029 — Hospedagem na Azure: uma VM com Docker Compose e deploy sem SSH

**Data:** 2026-11-26 · **Status:** aceito; a infraestrutura está criada, e a produção só troca de
endereço no corte (ver "Não verificado") · **Fase:** fatia 15 · substitui o ADR-0011 depois do corte

## Contexto

O Portfolio Playbook não aceita o Render como ambiente produtivo, e proíbe deploy por SSH ou FTP.
Até aqui a produção era o plano gratuito do Render (frontend e backend) com o banco no Neon, nos
Estados Unidos (ADR-0011); o backend dormia depois de 15 min sem uso (ADR-0017).

O que existe para pagar a troca é a assinatura **Azure for Students** da Católica SC, conferida em
26/11/2026 só com comandos de leitura:

- **US$ 100 de crédito no total**, não por mês. A cobrança sai em reais (≈ R$ 538). O limite de
  gasto está ligado: quando o crédito acaba, a assinatura é desativada e o site cai.
- Uma política da instituição libera só cinco regiões: `brazilsouth`, `chilecentral`,
  `italynorth`, `southafricanorth` e `belgiumcentral`.
- Os tamanhos de VM mais baratos (B1ms, B1s, B2s) estão bloqueados nas cinco, e em `brazilsouth`
  a série B inteira.
- Toda alteração de recurso exige autenticação em dois fatores.

## Opções consideradas

- **Ficar no Render:** recusada pelo Playbook.
- **VM em `brazilsouth`:** o tamanho liberado mais barato (F1als_v7, 2 GB) custa ≈ US$ 79 por mês
  com disco e IP. O crédito duraria ≈ 1,3 mês, menos que o tempo até a banca.
- **Serviços gerenciados da Azure** (aplicação em contêiner e Postgres gerenciado): cada peça é
  cobrada à parte. Não foi orçada em detalhe; a arquitetura de uma VM veio definida no pedido da
  fatia, e o custo dela é um número só, conhecido antes de criar.
- **Uma VM em `chilecentral` com Docker Compose** (escolhida).

## Decisão

**Região e tamanho.** `chilecentral` é a região liberada mais próxima do Brasil em que a série B
existe. Preços de tabela, 730 horas por mês, com disco SSD padrão de 32 GB e IP fixo:

| Tamanho | Memória | VM | Total por mês | Por dia |
|---|---|---|---|---|
| `Standard_B2als_v2` (até o Demo Day, 16/12) | 4 GB | US$ 38,40 | ≈ US$ 45,50 | ≈ US$ 1,50 |
| `Standard_B2ats_v2` (depois) | 1 GB | US$ 9,64 | ≈ US$ 16,75 | ≈ US$ 0,55 |

O tamanho é um parâmetro do Bicep: baixar é reaplicar, com uns 2 minutos de parada. Cofre,
armazenamento dos backups e tráfego somam centavos. O gasto começou em 26/11/2026.

**O que roda na VM** (`infra/compose.yml`): Caddy, frontend, backend e Postgres 16, cada um num
contêiner. Só o Caddy publica porta. O grupo de segurança de rede libera só 80 e 443; o Postgres
não tem porta nem na própria VM. Os logs dos contêineres giram (5 arquivos de 10 MB). O Ubuntu
aplica as atualizações de segurança sozinho e, quando uma pede, reinicia às 07:30 UTC (04:30 de
Brasília). O Redis fica de fora: o código não o usa em produção.

**HTTPS.** O Caddy pede e renova o certificado sozinho, e manda HSTS de um ano. O endereço é o
rótulo DNS da própria Azure, `verifyscan.chilecentral.cloudapp.azure.com`. Como
`cloudapp.azure.com` **não está na Public Suffix List** (conferido na lista oficial), o limite
semanal do Let's Encrypt é contado sobre `azure.com` inteiro, e pode esgotar por uso de terceiros.
A saída é o Caddy cair para o ZeroSSL, e isso **só acontece com um e-mail configurado** (notas da
versão 2.8.0 do Caddy). O e-mail vem do cofre (`EMAIL-ACME`), como os outros valores, e não está
em nenhum arquivo versionado.

**Cookie de sessão `__Host-vs_sessao`.** Pelo mesmo motivo da lista, outro site hospedado em
`*.cloudapp.azure.com` poderia gravar um cookie `vs_sessao` para o nosso endereço e fixar a sessão
de alguém. O prefixo `__Host-` faz o navegador aceitar o cookie só do próprio host, com `Secure` e
`Path=/`. Vale quando `COOKIE_SECURE=true`; em desenvolvimento o nome segue sem o prefixo. **As
sessões abertas caem no corte:** muda o endereço e muda o nome do cookie.

**O IP de quem pede (ADR-0024).** A cota de quem não tem conta é pelo HMAC do IP, e o `proxy.ts`
usa a entrada mais à direita do `X-Forwarded-For`. O Caddy escreve nesse cabeçalho o IP da conexão
e descarta o que o visitante mandou. O Caddy já faz isso sem configuração; a linha está no
`Caddyfile` para ficar visível. Um job do CI sobe a pilha inteira e confere de fora: seis
cadastros com seis `X-Forwarded-For` forjados esbarram no limite de 5 por IP, e um segundo cliente,
com outro IP, passa.

**O log do Caddy não leva dado do pedido (invariante 2).** Não há log de acesso. O log de erro, que
o Caddy escreve quando o frontend não responde, traz por padrão o IP, a URL com a query e os
cabeçalhos: um filtro apaga o pedido inteiro dessa linha, e o CI provoca o erro e confere.

**Segredos.** Ficam num Key Vault. A VM os lê com a identidade dela, sem senha nem arquivo de
credencial, a cada deploy, e os escreve num arquivo que só o root lê. Os **nomes** são criados por
script, com o valor `PREENCHER`; os **valores** quem coloca é o Walter, pelo portal. Os segredos
não estão no Bicep porque reaplicá-lo sobrescreveria os valores. O `IP_HMAC_SEGREDO` é o mesmo do
Render: trocá-lo zeraria as cotas do dia.

**Imagens.** Construídas no GitHub Actions e publicadas no registro do GitHub com o SHA do commit
como tag. São públicas, para a VM baixar sem credencial, e por isso não levam segredo: no frontend
entram só as `NEXT_PUBLIC_*`, que o Next grava no JavaScript do navegador de qualquer jeito; o
`PROXY_SEGREDO` é lido em execução.

**Deploy sem SSH** (`.github/workflows/deploy.yml`, `infra/vm/`). Depois do CI verde num push na
`master`:

1. o GitHub prova quem é à Azure por um token curto (OIDC). Não há senha guardada. A identidade
   do deploy só aceita o ambiente `producao` do GitHub, restrito à `master`, e só pode uma coisa:
   rodar comando naquela VM (papel próprio, `infra/main.bicep`);
2. o workflow manda o `entrar.sh` à VM pelo *run-command*. A VM baixa do repositório, que é
   público, os arquivos de `infra/` daquele commit, lê o cofre, baixa as imagens, sobe o banco,
   roda as migrações e sobe o resto;
3. a VM pergunta ao próprio site, pelo endereço público, se o `/health` responde. Se não
   responder, **volta sozinha para a versão anterior**;
4. o workflow só passa se a saída trouxer `DEPLOY_OK`, e confere o `/health` de fora.

O passo 4 existe porque o `az vm run-command invoke` responde "succeeded" mesmo quando o script
sai com erro (visto em 26/11/2026). Um deploy por vez: `concurrency` no workflow e uma trava de
arquivo na VM.

A porta 22 está fechada no grupo de segurança, o login por senha está desligado, e cada deploy
desliga e mascara o serviço de SSH dentro da VM. A Azure exige uma chave SSH na criação: foi
gerada, e a parte privada, apagada. O acesso de emergência é o run-command.

**Voltar uma versão.** Sozinha, quando o deploy falha; ou à mão, rodando o workflow com o SHA de
um commit anterior da `master`. A volta troca as imagens e os arquivos; **não desfaz migração**.
Por isso toda migração segue aditiva: a versão anterior tem de rodar com o banco já migrado.

**Backup.** Todo dia às 06:00 UTC (03:00 de Brasília), um temporizador do systemd roda o
`pg_dump`. A cópia vai do contêiner para a memória e daí para o armazenamento da Azure, com a
identidade da VM; nunca vira arquivo na VM. Ficam 7 dias: depois de gravar a cópia nova, o script
apaga as de 7 dias ou mais, e uma regra do próprio armazenamento faz o mesmo, como rede de
segurança. É o que o aviso de privacidade promete: o que a pessoa apagou some das cópias em até 7
dias. A conta de armazenamento não aceita chave de conta nem acesso público, e não guarda versão
apagada. Se o backup ou uma restauração falha, a VM manda um evento ao Sentry do backend, que já
avisa por e-mail: só o que falhou e um motivo curto, sem IP, sem nome de máquina e sem a saída de
erro do Postgres.

**Migração dos dados do Neon.** Um script que a própria VM roda. A string do Neon fica num segredo
temporário do cofre, que o Walter cria e apaga; ela vai só no ambiente do processo, e uma mensagem
de erro sai sem host, usuário, senha, banco nem IP. O script conta as linhas de cada tabela na
origem, para o site, copia numa transação só, conta de novo dos dois lados e só passa se a origem
não mudou durante a cópia e o destino tem as mesmas contagens e a mesma versão do Alembic. São
duas rodadas: uma para validar e outra logo antes do corte, porque o Render segue no ar até lá.

**Infraestrutura como código** (`infra/main.bicep`, aplicada com `az deployment group create`).
Dezessete recursos declarados, no grupo `rg-verifyscan`. O que prepara a VM (Docker, atualizações, swap) roda
uma vez, na criação; o que muda com o tempo (compose, Caddyfile, scripts, agendamento do backup)
chega pelo deploy.

**Privacidade (LGPD, art. 33).** Os dados passam dos Estados Unidos para o Chile: continua sendo
transferência internacional, e o aviso de privacidade diz o país, o provedor e os 7 dias das
cópias. Enquanto os dois ambientes existem, a imagem da VM mostra o texto da Azure e o Render
mostra o antigo.

**Orçamento.** Um orçamento de R$ 538 na assinatura, com aviso por e-mail em 60% e em 85%. A
Azure aceitou criá-lo, mas não há como saber antes se o aviso dispara nesta oferta (a API de
custos recusa a consulta). Por isso o saldo é conferido à mão no portal: em 03/12, 10/12 e 17/12
(depois de baixar o tamanho), e no dia 1º de cada mês.

## Consequências

- **O serviço não dorme mais** (RNF07, errata 18). A espera do ADR-0017 continua no código e
  deixa de aparecer; sai na limpeza depois do corte.
- **Um ponto único de falha.** Uma VM, um disco, uma zona. Se a VM cair, o site cai. O que sobra
  fora dela são as cópias diárias: perder a VM custa, no pior caso, um dia de dados.
- **Pequenas paradas previstas:** alguns segundos de erro a cada deploy, enquanto os contêineres
  trocam, e um reinício de madrugada quando uma atualização de segurança pede.
- **O crédito é finito.** Com 4 GB até 16/12 e 1 GB depois, a conta de tabela leva até por volta
  de abril de 2027. Sem crédito, a assinatura é desativada.
- **O tamanho de 1 GB pode sair de graça.** A página do Azure for Students lista 750 horas por
  mês do B2ats_v2 por 12 meses. Não foi confirmado nesta assinatura: confere-se no portal
  ("Serviços gratuitos") ou pelo saldo depois da troca.
- **`/metrics` deixou de ser alcançável de fora.** O backend não é mais público, e o Caddy só
  repassa o que o frontend atende. Consultar as métricas na VM fica pendente.
- **O run-command é a única porta.** Um comando por vez, e só os últimos 4 KB da saída. Ver log
  é por ele (`docs/deploy.md`), aos pedaços.
- **O log do deploy é público.** O repositório é público, e a saída da VM aparece no Actions. Os
  scripts não imprimem segredo, e há teste com valor marcado para cada saída.
- **Aviso de falha do backup, com um limite.** Falhas com o mesmo motivo viram uma ocorrência só
  no Sentry; a regra de e-mail avisa na primeira, quando ela volta depois de resolvida ou quando
  escala. Duas noites seguidas com o mesmo erro podem render um e-mail só.
- **O teste da cadeia de IP não cobre tudo.** No CI os clientes estão na mesma rede do Docker. Na
  VM o IP passa pela publicação de porta do Docker, o que só se confere no ar, com dois IPs reais.
- **Memória.** Parada, a pilha ocupa ≈ 310 MB. Com 1 GB há swap de 2 GB como folga; o
  comportamento sob uso só se conhece depois da troca de tamanho.
- **Para reaplicar o Bicep** é preciso passar a mesma chave SSH pública, e o preparo da VM não
  roda de novo numa VM que já existe.
- **Depois do corte, sai:** o texto do Render no aviso de privacidade e a variável
  `NEXT_PUBLIC_HOSPEDAGEM`, o `RENDER_GIT_COMMIT`, o `NEXT_PUBLIC_URL_DESPERTAR` e os passos do
  Render no README.

## Não verificado, em 26/11/2026

O workflow de deploy só existe para o GitHub depois do merge na `master`. Até lá, nada disto
rodou de verdade:

- o primeiro deploy, a emissão do certificado e o login da Azure a partir do Actions;
- as chamadas ao armazenamento, o backup, a restauração e a migração (testados só com falsos);
- o aviso do orçamento por e-mail e a gratuidade do B2ats_v2.

Rodou na VM: o preparo (Docker, atualizações, swap), a leitura do cofre com a identidade, o SSH
desligado, a recusa do deploy com o cofre vazio e o evento de teste do aviso, aceito pelo Sentry.
O que o primeiro deploy e o corte mostrarem entra aqui como adendo.
