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

**O que é analisado** (`sonar-project.properties`, na raiz):

- fontes: `backend/app`, `frontend` (sem `node_modules`, `.next`, `coverage` e `next-env.d.ts`) e
  `.github`;
- testes, marcados como teste e não como fonte: `backend/tests` e os `*.test.ts(x)` do frontend;
- fora: `corpus/` (é dado de teste; o caso 0035 tem um caractere de inversão de texto de
  propósito), `backend/tools` e `backend/alembic`.

**Cobertura importada, não medida pelo Sonar.** O job do backend gera o `coverage.xml` e o do
frontend o `coverage/lcov.info`, com os mesmos comandos do ADR-0025; os dois sobem como artifact e
o job `sonar` os baixa. As exclusões batem com as nossas: no backend conta `app/` inteiro; no
frontend só `app/**`, então os arquivos da raiz do frontend ficam fora da cobertura (continuam
sendo analisados). Dois ajustes para o Sonar achar os arquivos: o `lcov` é escrito com caminhos a
partir da raiz do repositório (`projectRoot: ".."` no `vitest.config.ts`), e o `<source>` do
`coverage.xml` é reescrito no job para o caminho do checkout.

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
| 10 | `python:S8786` | `formulator/limpeza.py` (padrão de e-mail) | Regex com tempo quadrático | **Real.** Medido: `a%a%a%…` com 16 mil caracteres levava 0,2 s. O padrão roda na saída da IA e na transcrição do print. | `%` no trecho de trás; mesmos casamentos, teste de tempo (< 50 ms). |
| 11 | `typescript:S8786` (2×) | `_lib/servidor.ts`, `next.config.ts` | Regex `/\/+$/` | **Falso positivo na prática.** A entrada é variável de ambiente nossa, não de visitante. | Ignorada nos dois arquivos. |
| 12 | `typescript:S4822` | `_lib/servidor.ts` (`despertar`) | `try` em volta de `fetch().catch()` | **Falso positivo.** O `try` pega o `fetch` que lança na hora; o `.catch`, a rejeição. | Ignorada nesse arquivo. |
| 13 | `python:S5863` | `tests/test_sortear_divisao.py` | Assert com a mesma expressão dos dois lados | **Falso positivo.** São duas chamadas: o teste é que a mesma semente repete o sorteio. | Ignorada nesse arquivo. |
| 14 | `python:S8414` | `backend/app/main.py` | CORS não é o último middleware | **Aceitável.** O middleware de requisição fica por fora de propósito (ADR-0026) e nunca responde sozinho. | Ignorada nesse arquivo. |

## Consequências

- **O "ignorada nesse arquivo" vale para a regra no arquivo inteiro**, não só para a linha da
  triagem: é o menor escopo que o `sonar-project.properties` oferece. Uma ocorrência nova da mesma
  regra no mesmo arquivo não aparece. Vale mais para o `ci.yml` (senha e `--no-build`).
- **O número de cobertura do Sonar pode não ser igual ao nosso no frontend.** O `lcov` leva dados
  de ramos, e a métrica "coverage" do Sonar mistura linhas e ramos; a comparável com o Vitest é a
  "line coverage". No backend o relatório só tem linhas. O Sonar mostra um número do projeto; por
  lado, é preciso olhar por pasta.
- **A cobertura do backend no Sonar é a do CI**, com os testes de integração (≈96%), não a da
  máquina sem Docker (≈93%).
- O `npm ci --ignore-scripts` vale só para o CI. O build de produção não mudou.
- Pendente: confirmar na primeira análise pelo CI que os dois relatórios foram resolvidos, que as
  questões ignoradas sumiram e que as corrigidas fecharam; depois, ligar o bloqueio do Quality
  Gate.
