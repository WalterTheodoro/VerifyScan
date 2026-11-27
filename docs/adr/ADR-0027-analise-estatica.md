# ADR-0027 — Análise estática com SonarQube Cloud

**Data:** 2026-11-25 · **Status:** aceito · **Fase:** fatia 13

## Contexto

O Portfolio Playbook exige análise estática do código. O projeto já tinha `ruff`, `mypy`, ESLint e
`tsc` no CI, que pegam estilo e tipo, mas nada que olhasse segurança, padrões de erro e os próprios
workflows do CI, nem um painel público com a cobertura.

O projeto já estava cadastrado no SonarQube Cloud, com a **análise automática** ligada: ela lê o
repositório sozinha, sem configuração nossa e sem a cobertura. A única análise feita assim (commit
`fdd27ee`) abriu 32 questões e mostrava cobertura vazia.

## Opções consideradas

- **Só as ferramentas que já rodam** (`ruff`, `mypy`, ESLint, `tsc`): não atende ao requisito e
  não olha segurança.
- **Análise automática do SonarQube Cloud:** zero configuração, mas não importa cobertura, não
  deixa escolher o que é fonte e o que é teste, e o que foi analisado não fica versionado.
- **Análise pelo CI, com `sonar-project.properties` versionado** (escolhida): o escopo, a
  cobertura e cada questão aceita ficam no repositório, com o motivo ao lado.

## Decisão

**SonarQube Cloud, rodado só pelo CI.** É gratuito para projeto público, cobre Python,
TypeScript e os workflows do GitHub Actions numa ferramenta só, e é o que o Playbook cita. A
análise automática foi desligada no painel.

**O que é analisado** (`sonar-project.properties`, na raiz). As fontes são o repositório inteiro
(`sonar.sources=.`), menos as exclusões da tabela. Os testes são declarados como teste
(`sonar.tests` e `sonar.test.inclusions`): `backend/tests/**`, os `*.test.ts(x)` do frontend e o
`vitest.setup.ts`. São analisados, mas não contam na cobertura nem nas linhas de código. Os mesmos
padrões estão em `sonar.exclusions`, que só vale para fontes, para nenhum arquivo ser indexado
duas vezes.

Essa declaração só tem efeito porque o job desliga a **configuração automática do scanner**
(`-Dsonar.scanner.autoconfig.enabled=false`); ver "Resultado na master", abaixo.

| Fora de quê | O quê | Por quê |
|---|---|---|
| Da análise | `corpus/**` | É dado de teste, não código. O caso 0035 tem um caractere de inversão de texto de propósito. |
| Da análise | `docs/**` | Documentação e o PDF do RFC. |
| Da análise | PDF, ícones e imagens | Binários e estáticos; o scanner tentava lê-los como texto. |
| Da análise | `node_modules`, `.next`, `coverage`, `next-env.d.ts` | Instalados ou gerados. |
| Só da cobertura | `backend/tools/**` | Scripts de avaliação, rodados à mão; o pytest-cov mede `backend/app`. |
| Só da cobertura | `backend/alembic/**` | Migrações: conferidas pelo `alembic check` e pelos testes de integração, não por teste de linha. |
| Só da cobertura | `*.config.ts`, `*.config.mjs`, `vitest.setup.ts` do frontend | Configuração, não código do produto. |
| Só da cobertura | `.github/**` | Workflows. |

O que sai "só da cobertura" continua sendo analisado: as regras rodam nele.

**Cobertura importada, não medida pelo Sonar.** O job do backend gera o `coverage.xml` e o do
frontend o `coverage/lcov.info`; os dois sobem como artifact e o job `sonar` os baixa. O que conta
é o mesmo dos dois lados: no backend, `app/` inteiro; no frontend, `app/**` mais os três arquivos
de código da raiz (`proxy.ts`, `instrumentation.ts`, `instrumentation-client.ts`). Esses três
ficavam fora da nossa medida (ADR-0025 media só `app/**`); entraram no Vitest em vez de saírem do
Sonar, para não esconder código. Dois ajustes para o Sonar achar os arquivos: o `lcov` é escrito
com caminhos a partir da raiz do repositório (`projectRoot: ".."` no `vitest.config.ts`), e o
`<source>` do `coverage.xml` é reescrito no job para o caminho do checkout.

**O Quality Gate ainda não bloqueia o merge.** O job não usa `sonar.qualitygate.wait`: ele envia a
análise e termina. Motivo: a primeira análise pelo CI muda o escopo e o conjunto de questões, e
bloquear antes de ver esse resultado poderia travar o merge por algo que ainda nem foi triado.
Bloquear fica para uma fatia depois de as questões estarem limpas.

**Actions de terceiros presas pelo commit**, com a tag num comentário: `astral-sh/setup-uv`
(v5.4.2, a mesma que a tag `v5` apontava) e `SonarSource/sonarqube-scan-action` (v8.4.1, de
03/11/2026; a v8.5.0, de 13/11, tinha 12 dias e fica para depois, pelo ADR-0022). As `actions/*`
são do próprio GitHub e seguem pela tag da versão maior.

**PR de fork** não recebe o `SONAR_TOKEN`: o job `sonar` é pulado por um `if`, não falha.

## Triagem das 32 questões da análise automática

Lidas pela API pública em 25/11/2026. Nenhum *security hotspot* aberto.

| # | Regra | Onde | O que é | Classificação e justificativa | O que foi feito |
|---|---|---|---|---|---|
| 1 | `githubactions:S7637` | `ci.yml` (setup-uv) | Action de terceiro presa por tag | **Real.** A tag pode ser movida para outro código. | Presa pelo commit. |
| 2 | `githubactions:S8544` (6×) | `ci.yml`, cada `uv run` | `uv run` sem travar no lock | **Real.** Sem `--locked` o `uv run` pode resolver de novo. O comentário do CI dizia que o `--frozen` reprovava lock desatualizado; quem faz isso é o `--locked`. | `--locked` no `uv sync` e em todo `uv run`; comentário corrigido. |
| 3 | `githubactions:S8541` (7×) | `ci.yml`, cada `uv` | `uv` sem `--no-build` | **Aceitável.** O próprio backend é um pacote que o `uv` precisa construir; `--no-build` quebraria a instalação. | Ignorada nesse arquivo. |
| 4 | `githubactions:S6505` | `ci.yml` (`npm ci`) | Instalação roda scripts dos pacotes | **Real (endurecimento).** Testado: com `--ignore-scripts`, lint, `tsc`, 193 testes e build passam igual. | `npm ci --ignore-scripts`. |
| 5 | `githubactions:S6505` e `S8543` (2× cada) | `ci.yml` (`npx next typegen`, `npx tsc`) | `npx` poderia baixar pacote | **Falso positivo na prática:** os dois vêm do `npm ci`. Fechado mesmo assim, por custar uma palavra. | `npx --no-install`. |
| 6 | `secrets:S6698` (2×), `yaml:S2068` | `ci.yml` (Postgres do job) | Senha no arquivo | **Aceitável.** Senha descartável: o banco só existe dentro do runner. | Ignoradas nesse arquivo. |
| 7 | `secrets:S6698` | `backend/app/core/config.py` | Senha no default do `database_url` | **Aceitável.** É a do docker compose local; produção usa a variável de ambiente. | Ignorada nesse arquivo. |
| 8 | `python:S5332` (2×) | `analyzers/urls.py`, `analyzers/dominios.py` | `http://` no código | **Falso positivo.** É prefixo para o `urlsplit` separar o host; o sistema nunca abre o link (ADR-0022). | Ignorada nos dois arquivos. |
| 9 | `text:S6389` | `corpus/casos/0035-rtl-override.yaml` | Caractere bidirecional | **Aceitável.** É o caso de teste do golpe com inversão de texto. | `corpus/` saiu do escopo. |
| 10 | `python:S8786` | `formulator/limpeza.py` (padrão de e-mail) | Regex com tempo quadrático | **Real.** Medido: `a%a%a%…` com 16 mil caracteres levava 0,2 s. O padrão roda na saída da IA e na transcrição do print. | Reescrita em tempo linear (`trocar_emails`), com teste de tempo (< 50 ms) e teste de igualdade com o padrão antigo. Ver "A regex de e-mail", abaixo. |
| 11 | `typescript:S8786` (2×) | `_lib/servidor.ts`, `next.config.ts` | Regex `/\/+$/` | **Falso positivo na prática.** A entrada é variável de ambiente nossa, não de visitante. | Ignorada nos dois arquivos. |
| 12 | `typescript:S4822` | `_lib/servidor.ts` (`despertar`) | `try` em volta de `fetch().catch()` | **Falso positivo.** O `try` pega o `fetch` que lança na hora; o `.catch`, a rejeição. | Ignorada nesse arquivo. |
| 13 | `python:S5863` | `tests/test_sortear_divisao.py` | Assert com a mesma expressão dos dois lados | **Falso positivo.** São duas chamadas: o teste é que a mesma semente repete o sorteio. | Ignorada nesse arquivo. |
| 14 | `python:S8414` | `backend/app/main.py` | CORS não é o último middleware | **Aceitável.** O middleware de requisição fica por fora de propósito (ADR-0026) e nunca responde sozinho. | Ignorada nesse arquivo. |

## O que a primeira análise pelo CI mostrou (PR #31, 25/11/2026)

- **Os dois relatórios de cobertura foram lidos**, sem erro de caminho.
- **O escopo que eu tinha escrito foi ignorado.** A primeira versão usava `sonar.sources` e
  `sonar.tests`; o scanner avisa que não têm efeito e analisou os 462 arquivos, com o `corpus/`.
  `backend/tools` e `backend/alembic` entraram na cobertura com 0%, e o número do projeto saiu
  65,8%. Corrigido primeiro só com exclusões; a causa de verdade (a configuração automática do
  scanner) só apareceu depois, e está em "Resultado na master".
- **`prompt.py` não foi analisado:** o analisador de Python parou no campo `print` de
  `EntradaIA`. O campo é interno (não vai ao JSON da API nem ao esquema da IA) e foi renomeado
  para `captura`.
- **A regex de e-mail seguiu apontada**, mesmo com o tempo já linear na entrada medida.

### A regex de e-mail

A primeira correção (commit `9d3876f`) pôs o `%` no trecho de trás do padrão. Eu afirmei que os
casamentos não mudavam, e estava errado: em `a@b.c%d@e.com` o padrão original tirava os dois
e-mails e o corrigido deixava o segundo. Nenhum teste pegava; apareceu ao comparar os dois padrões
em entradas aleatórias. É um erro na direção perigosa, porque a limpeza existe para o e-mail não
chegar à tela.

A correção atual não mexe em onde um e-mail pode começar. O padrão casa toda sequência de
caracteres de nome de e-mail, e ela só conta como e-mail quando o grupo do domínio também casa;
casar a sequência mesmo sem domínio é o que impede a busca de recomeçar no meio dela. Os
quantificadores são possessivos (`++`, Python 3.11+). Como o padrão agora casa também o que não é
e-mail, ele não é mais usado direto: a troca é feita por `trocar_emails`. Três testes guardam
isso: o caso acima, 20 mil entradas aleatórias com semente fixa comparadas com o padrão original, e
o de tempo. Se o Sonar seguir apontando a regra, ela será ignorada nesse arquivo, com o teste de
tempo como justificativa.

## Resultado na master

Análise do commit `8a35db2`, em 25/11/2026, conferida por arquivo pela API pública.

| | Antes (análise automática) | Agora |
|---|---|---|
| Segurança | E | **A** |
| Confiabilidade | C | **A** |
| Manutenibilidade | A | **A** |
| Questões abertas | 32 | **0** |
| *Security hotspots* | 0 | 0 |
| Quality Gate | — | passou |

| Cobertura | Sonar | Nossa medida |
|---|---|---|
| Backend (`backend/app`, 2885 linhas) | **96,3%** | 96,29% no CI (pytest-cov, com integração) |
| Frontend, linhas (1008 no Sonar, 880 no Vitest) | **52,9%** | 55,90% (Vitest) |
| Frontend, "coverage" (linhas e ramos) | **51,0%** | — |
| Projeto, o número do selo | **79,6%** | — |

Arquivos: 144 como fonte e 84 como teste (59 de `backend/tests`, 24 `*.test.ts(x)` e o
`vitest.setup.ts`). Linhas a cobrir só em `backend/app` (68 arquivos), `frontend/app` (48) e nos
três arquivos de código da raiz do frontend. `backend/tools` e `backend/alembic` são analisados e
não contam na cobertura. As 32 questões antigas constam como fechadas; a API não distingue a
corrigida da ignorada. Log sem `WARN` nem `ERROR`.

### A configuração automática do scanner, e o erro que ela escondeu

O SonarQube Cloud tem, em beta aberto desde 29/09/2026, a "configuração automática" do scanner
(`sonar.scanner.autoconfig.enabled`). Ligada, como estava neste projeto, ela ignora
`sonar.sources`, `sonar.tests` e `sonar.test.inclusions` e classifica os arquivos a partir do
sistema de build que encontra. Não era a action nem o diretório base: o log mostrava o arquivo de
propriedades lido, e depois as linhas `Detecting build system information` e um módulo
`verifyscan-backend`, o nome do `pyproject.toml`. Foi assim que `backend/tests` virou teste
sozinho (o `pyproject.toml` tem `testpaths`). Os testes do frontend não foram detectados.

O erro foi meu, em duas partes. Ao ver o aviso de que as propriedades não tinham efeito, troquei o
escopo por exclusões sem procurar a causa, e tirei a exclusão dos testes do frontend supondo que o
scanner os reconheceria como reconheceu os do backend. E dei a correção por conferida olhando a
análise do PR #31, que mostrava 79,6%. Na master (`6d81ca0`), os 24 arquivos de teste do frontend
entraram como código, com 1223 linhas a cobrir e 0%: frontend 23,9% de linhas, projeto 62,8%.

A correção (PR #32) desliga a configuração automática na linha de comando do scanner, que é onde a
documentação diz que o valor vence o do projeto, e declara fontes e testes no
`sonar-project.properties`. A documentação recomenda mesmo deixá-la desligada em projeto que tem
configuração própria.

## Camada complementar no GitHub

Ativadas no repositório, em 25/11/2026, pelas configurações do GitHub (não há arquivo no
repositório para isso):

- **Varredura de segredos** (*secret scanning*): procura credenciais no histórico e em cada push.
- **Proteção de push:** recusa o push que traz um segredo reconhecido, antes de ele entrar no
  repositório. É a trava da invariante 7 que o Sonar não dá: ele só vê o segredo depois de
  publicado.
- **Alertas do Dependabot:** avisam de dependência com falha conhecida. **Sem atualizações
  automáticas:** o Dependabot proporia a versão mais nova, e a regra dos 14 dias (ADR-0022) pede
  que cada atualização seja escolhida e datada à mão. O alerta diz o que olhar; quem atualiza
  continua sendo uma pessoa, com `--before`.

O Sonar olha o código que escrevemos; essas três olham segredos e dependências.

## Triagem do PR #34: a hospedagem na Azure (26/11/2026)

O PR da fatia 15 (ADR-0029) passou nos 12 checks do CI e reprovou no Quality Gate: nota **E** de
segurança no código novo, por 9 questões em arquivos que o projeto não tinha antes (Bicep, shell,
Dockerfile, workflow de deploy). Nenhum *security hotspot*; cobertura e duplicação passaram. A
nota E vem da única questão bloqueante (item 1), mas o gate exige nota A: as nove tinham de sair.

| # | Regra | Onde | O que é | Classificação e justificativa | O que foi feito |
|---|---|---|---|---|---|
| 1 | `python:S2115` (bloqueante) | `infra/vm/migrar_neon.py` | URL do banco de destino sem senha | **Falso positivo.** A senha existe e vem do cofre; vai na variável `PGPASSWORD`, fora da URL de propósito, para não aparecer na linha de comando. Há teste que confere. | Ignorada nesse arquivo. |
| 2 | `docker:S8541` | `backend/Dockerfile` | `uv sync` sem `--no-build` | **Real (endurecimento).** No `ci.yml` a mesma regra foi aceita porque lá o backend é instalado e precisa ser construído (item 3 da primeira triagem). Na imagem ele entra por cópia (`--no-install-project`). Testado: com `--no-build` a instalação passa, porque todas as dependências têm pacote pronto. | `--no-build` no `uv sync`. Quem testa é o job que constrói a imagem e sobe a pilha. |
| 3 | `shell:S6506` | `infra/vm/entrar.sh` | `curl` segue redirecionamento sem exigir HTTPS | **Real (endurecimento).** O que esse `curl` baixa roda como root na VM. | `--proto '=https' --proto-redir '=https'`, com teste que lê o script e reprova um `curl` sem as duas opções. |
| 4 | `githubactions:S7631` | `.github/workflows/deploy.yml` | Checkout do commit que disparou o workflow, num job com acesso à Azure | **Falso positivo.** O job só roda se o CI veio de um push (não de um PR), neste repositório, na `master`, e depois de um passo conferir que o commit pertence à `master`. Um PR de fork não passa por nenhuma das quatro. | Ignorada nesse arquivo. |
| 5 | `python:S1313` | `infra/vm/azure.py` | Endereço IP fixo `169.254.169.254` | **Falso positivo.** É o serviço de metadados da Azure, igual em toda VM e sem nome DNS: é por ele que a VM obtém o token da própria identidade. | Ignorada nesse arquivo. |
| 6 | `azureresourcemanager:S6388` | `infra/main.bicep` (disco da VM) | Disco sem chave de criptografia própria | **Aceitável.** O disco gerenciado já é cifrado em repouso pela Azure, com chave da plataforma. A regra pede chave gerenciada por nós, o que exigiria outro cofre, com proteção contra exclusão, e mais uma identidade, para proteger contra um risco (a Microsoft ler o disco) que não está no modelo de ameaças de um TCC. | Ignorada nesse arquivo. |
| 7 | `azureresourcemanager:S6388` | `infra/main.bicep` (VM) | VM sem `encryptionAtHost` | **Aceitável.** Ver "Por que não ligamos o `encryptionAtHost`", abaixo. | Ignorada nesse arquivo (a mesma linha do item 6). |
| 8 | `azureresourcemanager:S6388` | `infra/main.bicep` (conta de armazenamento) | Conta sem bloco `encryption` | **Aceitável.** O armazenamento da Azure é sempre cifrado em repouso com chave da plataforma, e isso não se desliga. | Ignorada nesse arquivo (a mesma linha do item 6). |
| 9 | `azureresourcemanager:S6378` | `infra/main.bicep` (conta de armazenamento) | Conta sem identidade gerenciada | **Falso positivo.** A conta não se autentica em nada. Quem a acessa é a VM, com identidade gerenciada e papel só no container dos backups; a chave de conta está desligada. | Ignorada nesse arquivo. |

**Por que não ligamos o `encryptionAtHost`.** O disco da VM, onde mora o banco, já é cifrado em
repouso pela Azure com chave da plataforma: é o padrão dos discos gerenciados. O
`encryptionAtHost` acrescenta a cifragem, no servidor físico, do cache do disco e do disco
temporário. Não foi ligado por três motivos: este tamanho de VM não tem disco temporário; ligar
exige registrar o recurso na assinatura e desligar a VM uma vez, e não se sabe se a assinatura de
estudante permite; e o ganho cobre quem tem acesso físico ao servidor da Azure. Fica como opção:
é uma linha no Bicep.

**O que não deu para ler.** A API pública do SonarQube Cloud não devolve o texto das regras sem
login, e as páginas públicas delas mudaram de endereço. A classificação saiu da mensagem de cada
questão e do que a Azure faz por padrão, não do texto da regra.

**Uma regra, três questões.** A linha que ignora a `S6388` no `main.bicep` cobre os itens 6, 7 e
8, e cobriria um quarto recurso de armazenamento que entrasse nesse arquivo sem criptografia. É o
limite já descrito em "Consequências": o menor escopo é a regra no arquivo.

## Consequências

- **O "ignorada nesse arquivo" vale para a regra no arquivo inteiro**, não só para a linha da
  triagem: é o menor escopo que o `sonar-project.properties` oferece. Uma ocorrência nova da mesma
  regra no mesmo arquivo não aparece. Vale mais para o `ci.yml` (senha e `--no-build`).
- **A cobertura do frontend no Sonar não é igual à do Vitest, e não tem como ser com este
  relatório.** Os arquivos são os mesmos; a conta é que muda. O `lcov` traz 128 linhas que têm
  dado de ramo mas não têm dado de linha (ramos de expressões que continuam na linha de baixo), e
  o Sonar as soma às linhas a cobrir: 880 viram 1008. Conferido contra a primeira análise: a mesma
  conta sobre o relatório daquele dia dá os 993 e os 51,5% que o Sonar mostrou. Além disso, a
  métrica "coverage" do Sonar mistura linhas e ramos. Medido: Vitest 55,90% de linhas; Sonar
  52,9% de linhas e 51,0% de "coverage". Igualar exigiria trocar o medidor de cobertura do
  Vitest, que é dependência nova; fica como opção.
- **O selo de cobertura mostra um número só, do projeto inteiro**, backend e frontend somados,
  com linhas e ramos: 79,6%. Não é nenhum dos dois números da prova de autoria.
- **A cobertura do backend no Sonar é a do CI**, com os testes de integração (96,3% na primeira
  análise), não a da máquina sem Docker (≈93%).
- O `npm ci --ignore-scripts` vale só para o CI. O build de produção não mudou.
- **A análise de PR não serve para conferir escopo.** Ela só expõe os arquivos que o PR alterou,
  e os totais dela saíram iguais (79,6%) com os testes classificados certo e errado. Mudança de
  escopo se confere na master, por arquivo.
- **A análise depende de um valor não documentado.** A documentação só descreve
  `sonar.scanner.autoconfig.enabled=true`; o `false` funcionou, mas o recurso está em beta e pode
  mudar. O sinal de que parou de valer é o `WARN` "configured but have no effect" no log do job.
- Pendente: ligar o bloqueio do Quality Gate.
