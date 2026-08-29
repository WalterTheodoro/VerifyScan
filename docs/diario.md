# Diário de bordo — VerifyScan

Registro honesto de cada sessão de trabalho: o que foi feito, o que deu errado e o que ficou
pendente. É matéria-prima do capítulo de metodologia da monografia — inclusive, e principalmente,
os erros.

---

## 2026-08-27 — Sessão 0: análise do RFC e decisões de fundação

### O que foi feito

- Trocado `docs/RFC-VerifyScan-v1.1.pdf` pela v1.1 real (ver abaixo).
- Criado `docs/analise-rfc-v1.1.md`: resumo do sistema, 14 achados contra a v1.1 (cada um com
  âncora de seção e status), as decisões 3.1–3.11 e as partes difíceis de defender numa banca.
- Criado `docs/errata-rfc-v1.1.md`: 7 correções no texto do RFC, cada uma dizendo onde entra e o
  que muda. **Não haverá RFC v1.2** — a errata de uma página é anexada ao documento na Fase 10.
- Criados `ADR-0001` a `ADR-0006`.
- Corrigidas as invariantes 2 e 8 do `CLAUDE.md`, por consequência do ADR-0006 e do ADR-0002.
- Nenhuma linha de código. A Fase 0 começa na próxima sessão.

### O que deu errado: a análise foi feita sobre o RFC errado

A primeira rodada desta sessão analisou `docs/RFC-VerifyScan-v1.1.pdf` e concluiu, entre outras
coisas, que RF12 e RF13 não existiam, que não havia requisito de operar sem a LLM, que a numeração
de seções do `CLAUDE.md` não batia com o documento e que o modelo de dados tinha quatro entidades
com uma tabela `URLVerificada` contradizendo o cache em Redis.

Tudo isso era verdade **sobre o arquivo que estava no repositório** — e o arquivo era a **v1.0**.
Ele tinha 21 páginas, 1 284 029 bytes, md5 `bed73a7d…` e trazia "Versão 1.0" na página de
identificação, apesar do nome `RFC-VerifyScan-v1.1.pdf`. A v1.1 real tem 40 páginas, 1 963 213
bytes, md5 `e5188c44…`, e contém RF13, RNF08, o pipeline em §5.4.x, três entidades no modelo de
dados e as seções 11 a 13 (contribuições e assinaturas).

**Causa:** o comando de setup usou curinga — `Copy-Item "$HOME\Downloads\RFC-VerifyScan*.pdf"` —
que casou cinco arquivos e copiou um por cima do outro. Sobrou o último em ordem alfabética,
`RFC-VerifyScan.pdf` (v1.0, de 23/jun), renomeado para `RFC-VerifyScan-v1.1.pdf`. O nome do
arquivo mentia sobre o conteúdo.

**Como foi detectado:** ao receber a contestação dos achados, a resposta não foi aceitá-la nem
insistir, e sim reabrir o PDF e extrair o texto — momento em que a divergência entre nome e
conteúdo apareceu, junto com a localização da v1.1 real em `~/Downloads`.

Vale registrar o que **não** aconteceu, porque a hipótese chegou a ser escrita: não houve confusão
entre as capturas de feedback das seções 11 e 13 e a descrição do documento atual. O PDF que estava
versionado não tem essas seções. O erro real foi mais simples e mais evitável — não desconfiar de
um arquivo chamado v1.1 que se identifica como v1.0 logo na segunda página.

**Efeito colateral:** o relatório da primeira rodada só existia no chat e se perdeu junto com o
contexto. Por isso a análise agora mora em `docs/analise-rfc-v1.1.md`, e por isso só quatro dos
achados originais puderam ser mapeados um a um na seção 2.1 daquele arquivo.

### Lição de processo (vale a partir de agora)

> Todo documento normativo em `docs/` carrega no diário a **contagem de páginas** e a **string de
> versão** conferidas na primeira leitura. Análise que cita um documento sem esse carimbo não é
> verificável — e foi exatamente isso que custou esta sessão.

Aplicado aqui: `docs/RFC-VerifyScan-v1.1.pdf` — 40 páginas, 1 963 213 bytes, md5
`e5188c44a6aaaf131161e67e5963e0eb`, campo "Versão" = 1.1, Julho de 2026. Conferido em 2026-08-27.

### Achado mais relevante da análise

As faixas de classificação (§5.4.7) nunca foram dimensionadas contra os pesos. A soma máxima da
tabela é 340 pontos e ALTO começa em 61 — 18% do máximo. Um SMS legítimo de banco
("Banco do Brasil informa" +15, "sua conta será suspensa" +15, "clique agora" +10) soma 40 e cai em
MÉDIO sem nenhum indicador de fraude. Como MÉDIO conta como golpe na métrica principal (ADR-0005),
esse caso vira falso positivo medido já na primeira execução da Fase 2 — o corpus denuncia o
problema sozinho. É o motivo de a definição da métrica vir antes da medição, e não depois.

### Pendências abertas

| Pendência | Natureza | Quando trava |
|---|---|---|
| **Comitê de ética / consentimento** | externa — coordenação do curso | **bloqueante da Fase 2** |
| **3.9 — cronograma** | decisão do autor | Fase 0 |
| **3.10 — deploy** | decisão do autor | Fase 9 |

**Comitê de ética.** O corpus da Fase 2 vai conter mensagens de familiares, colegas e phishing da
caixa pessoal. Isso é coleta de dados de pessoas. É preciso confirmar com a coordenação do curso se
o TCC exige submissão ao CEP e qual o registro de consentimento aceito. Se a exigência existir e
for descoberta só na Fase 9, o capítulo de resultados fica comprometido — o corpus inteiro estaria
coletado fora de conformidade. Pendência com destinatário externo: o tempo de resposta não depende
de nós, então precisa ser aberta antes do primeiro caso entrar em `corpus/casos/`.

**3.9 e 3.10** não foram decididos por escolha do autor — não decidir por ele.

### Próximo passo

Fase 0 do plano de execução: monorepo, `docker compose`, `/health`, `uv`, `ruff`, `mypy`,
`pytest`, Alembic (template async, ADR-0001), CI e README de setup para Windows.

---

## 2026-08-27 — Sessão 1: Fase 0, fundação do monorepo

### O que foi feito

- Estrutura da Seção 4 do `CLAUDE.md` criada, com todos os pacotes vazios já carimbados com a fase
  em que serão preenchidos. Um pacote a mais do que o `CLAUDE.md` prevê: `app/services/`, porque a
  regra "rotas finas, zero regra de negócio em `api/`" precisa de um lugar para a regra morar.
- `docker-compose.yml` com Postgres 16 e Redis 7, healthcheck nos dois e volumes nomeados.
  `POSTGRES_PASSWORD` **sem default de propósito**: o compose falha na hora se o `.env` não foi
  preenchido, em vez de subir um banco com senha vazia.
- `GET /health` checando Postgres (`SELECT 1`) e Redis (`PING`) em paralelo, reportando cada um
  separadamente com latência. 200 quando os dois respondem, 503 quando qualquer um falha — o corpo
  mantém o mesmo formato nos dois casos, porque é dele que a tela lê.
- Página no Next.js que consome `/health`. Sem estilo elaborado: é da Fase 1 a acessibilidade real.
- `.env.example` com todas as variáveis até a Fase 8, agrupadas por fase, sem nenhum valor real.
- CI no GitHub Actions com dois jobs: backend (`ruff format --check`, `ruff check`, `mypy`,
  `pytest`) e frontend (`npm ci`, `npm run lint`).
- README com setup para Windows, incluindo a instalação do Tesseract com o pacote `por` — que só
  será usado na Fase 5, mas é o passo que mais trava quem tenta rodar o projeto.
- `corpus/README.md` criado vazio de casos, já com o procedimento de anonimização e o lembrete da
  pendência do comitê de ética. O diretório existe desde agora para que nenhum caso entre sem
  proveniência.

### Decisões tomadas no caminho (nenhuma virou ADR — todas são consequência de ADR existente)

- **`/health` devolve 503 quando degradado.** É o que orquestrador e monitoramento esperam. O corpo
  não muda de formato, então o frontend lê os dois casos com o mesmo código.
- **Os verificadores entram na rota por `Depends`, atrás de um `Protocol`.** É o que permite o
  teste sem rede exigido pela Seção 6 do `CLAUDE.md`, e é o mesmo desenho que a Fase 4 vai usar
  para o `ProvedorReputacao`.
- **Timeout explícito já em `/health`** (`TIMEOUT_HEALTH_S`, 2s). O ADR-0002 vale desde a Fase 0;
  não faz sentido abrir exceção justamente na primeira rota.
- **A URL do banco não fica no `alembic.ini`.** O `env.py` lê `DATABASE_URL` das `Settings`; a linha
  `sqlalchemy.url` do template ficou comentada, porque o `.ini` é versionado (invariante 7).
- **O detalhe do erro em `/health` é truncado e só traz a primeira linha da exceção.** Erros de
  conexão do psycopg trazem host, porta e usuário em várias linhas, e o corpo de `/health` é
  público.

### Test-first, e onde ele foi de fato aplicado

Os quatro testes de `/health` foram escritos antes do service e da rota, e a primeira execução
falhou com `ModuleNotFoundError: No module named 'app.main'` — o que é o comportamento pretendido,
e ficou registrado aqui porque é o tipo de detalhe que o capítulo de metodologia precisa. O resto
da fase (compose, CI, README) não tem comportamento verificável por teste e foi escrito direto.

O quarto teste é o que menos parece teste e mais importa: ele afirma que, depois de uma requisição
a `/health`, `app.state` **não** tem `engine` nem `redis`. Como esses dois só nascem no `lifespan`,
que o transporte em memória não executa, o teste quebra no dia em que alguém abrir conexão dentro
da rota. É a guarda da regra "teste não faz chamada de rede, nunca".

### O que deu errado

**1. O `readme = "../README.md"` quebrou o `uv sync`.** O hatchling recusa caminho de readme fora
do diretório do projeto (`Readme path must be within the project directory`). O `pyproject.toml` do
backend apontava para o README da raiz do monorepo. Removida a linha — o backend não é um pacote
distribuível, e a descrição do projeto mora no README da raiz de qualquer jeito.

**2. O `create-next-app` gerou código que não passa no próprio lint.** A página inicial usava
`useEffect` chamando uma função que começa com `setState`, e o `eslint-config-next` reprovou com
`react-hooks/set-state-in-effect` ("Calling setState synchronously within an effect can trigger
cascading renders"). Duas tentativas até acertar: mover o `setState` para depois do primeiro
`await` **não** resolveu — a regra não modela a fronteira do `async`. O que resolveu foi extrair
`consultarSaude()` como função pura, que só busca e traduz a resposta, e deixar o `setState` dentro
do callback do `.then()` — que é exatamente o escape documentado pela regra. De quebra, a flag
`ativo` no cleanup passou a descartar a resposta que chega depois de a página sair da tela.
A regra não foi desligada.

**3. O `create-next-app` deixou lixo de template.** Ele gera `frontend/CLAUDE.md` e
`frontend/AGENTS.md` além do `README.md` boilerplate da Vercel. O `CLAUDE.md` aninhado competiria
com o arquivo de contexto do projeto; os três foram removidos. O `.gitignore` dele também ignora
`.env*`, o que engoliria o `.env.local.example` — corrigido com uma exceção explícita.

### Verificação

| Comando | Resultado |
|---|---|
| `uv run ruff format --check .` | 25 arquivos já formatados |
| `uv run ruff check .` | All checks passed |
| `uv run mypy app` | Success: no issues found in 20 source files |
| `uv run pytest -q` | 4 passed |
| `npm run lint` (frontend) | limpo |
| `npx tsc --noEmit` (frontend) | limpo |
| `npm run build` (frontend) | compila, 2 rotas estáticas |

### O Gate 0 não fechou — e o motivo

O Gate 0 exige `docker compose up -d` seguido dos comandos do README chegando em `/health` com os
dois serviços OK. **O Docker Desktop não estava instalado nesta máquina** (nem no `PATH`, nem em
`C:\Program Files\Docker`), e a instalação exige instalador gráfico e reinício. A parte
automatizada do Definition of Done fechou; a parte que precisa de infraestrutura real ficou
pendente e será executada assim que o Docker estiver disponível.

Duas afirmações do README ainda **não** foram verificadas contra serviço real e precisam ser
conferidas nessa hora:

1. que `uv run alembic upgrade head` termina sem erro com o diretório `versions/` vazio;
2. que `/health` responde `status: ok` com os dois serviços de pé.

### Pendências abertas

| Pendência | Natureza | Quando trava |
|---|---|---|
| **Fechar o Gate 0 com Docker rodando** | ambiente | antes de começar a Fase 1 |
| **Comitê de ética / consentimento** | externa — coordenação do curso | **bloqueante da Fase 2** |
| **3.9 — cronograma** | decisão do autor | Fase 0 |
| **3.10 — deploy** | decisão do autor | Fase 9 |

As pendências 3.9 e 3.10 continuam abertas: são decisões do autor e não foram tomadas por ele.

### Próximo passo

Fase 1 do plano de execução: `POST /api/analises` com `TextAnalyzer`, `URLExtractor`,
`ScoringEngine` e `scoring/regras.yaml`, mais as telas de análise e resultado.

---

## 2026-08-28 — Sessão 2: fechamento do Gate 0

Docker Desktop instalado desde a sessão anterior (`Docker 29.7.2`, `Compose v5.4.0`, `hello-world`
executou). Esta sessão existe só para rodar contra infraestrutura real o que a sessão 1 não pôde
rodar — e o Gate encontrou um bug que nenhum teste teria pego.

### O que foi feito

- `app/services/` documentado na Seção 4 do `CLAUDE.md`. O pacote existia no disco desde a sessão
  1 mas não na estrutura de referência; a regra "rotas finas, zero regra de negócio em `api/`"
  não dizia para onde a regra deveria ir.
- Comandos do README executados na ordem exata, do `Copy-Item .env.example .env` ao
  `npm run dev`.
- Corrigido `alembic/env.py` (ver abaixo).
- As duas afirmações não verificadas do README foram conferidas: uma era falsa.

### Afirmação 1 do README — **era falsa**

> "O `alembic upgrade head` termina sem fazer nada nesta fase; rodá-lo serve para provar que a
> conexão com o banco funciona."

Com Postgres `healthy` e `DATABASE_URL` correta, o comando saiu com código 1:

```
psycopg.InterfaceError: Psycopg cannot use the 'ProactorEventLoop' to run in async mode.
```

**Causa.** No Windows, o event loop padrão do `asyncio` é o `ProactorEventLoop`, e o `psycopg` em
modo async se recusa a rodar nele — ele precisa do `SelectorEventLoop`. O `env.py` do template
async do Alembic chama `asyncio.run(...)` cru, então herda o loop padrão da plataforma. Isso não
tem nada a ver com o `versions/` estar vazio: a conexão morre antes de o Alembic olhar para as
migrações.

**Correção.** Três linhas em `run_migrations_online()`, com o `loop_factory` do `asyncio.run`
(Python 3.12+) sob guarda de `sys.platform == "win32"`. Depois disso, `EXIT=0`:

```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
```

Com isso a afirmação do README passa a ser verdadeira e o texto dele não precisou mudar.

**Não houve teste antes do código, e o motivo importa.** O comportamento verificável aqui é
"conectar num Postgres real". A Seção 6 do `CLAUDE.md` proíbe teste que faça chamada de rede, então
não existe teste possível para isso — a verificação é o próprio comando, e é por isso que o Gate 0
é um passo manual do plano e não um item da suíte. Este bug sobreviveu a `ruff`, `mypy`, `pytest` e
CI verdes na sessão 1.

### Afirmação 2 do README — **confirmada**

Com o comando documentado (`uv run uvicorn app.main:app --reload --port 8000`):

```
status postgres                                 redis
------ --------                                 -----
ok     @{status=ok; latencia_ms=3,18; detalhe=} @{status=ok; latencia_ms=0,88; detalhe=}
```

Conferido também o caminho que o navegador de fato usa — `GET /health` com
`Origin: http://localhost:3000` devolve `200` e `access-control-allow-origin: http://localhost:3000`.
A página em `localhost:3000` responde `200` e monta; a leitura dos dois serviços acontece no
cliente, então o HTML servido mostra "Consultando a API…" e não serve como evidência — o que serve
é a resposta com `Origin` acima.

### Achado colateral: **sem `--reload`, o backend não fala com o Postgres**

Rodando `uv run uvicorn app.main:app --port 8000` (sem `--reload`), `/health` devolve `503`:

```json
{"status":"degradado","postgres":{"status":"erro","latencia_ms":0.37,
 "detalhe":"InterfaceError: (psycopg.InterfaceError) Psycopg cannot use the 'ProactorEventLoop'…"},
 "redis":{"status":"ok","latencia_ms":23.08,"detalhe":null}}
```

É a mesma causa do bug do Alembic. O `--reload` mascara o problema por acidente: o
`asyncio_loop_factory` do uvicorn devolve `ProactorEventLoop` no Windows **exceto** quando a
aplicação roda em subprocesso, que é justamente o modo do `--reload`. Como o README documenta o
comando com `--reload`, o texto dele está correto — mas o processo de produção da Fase 9 não terá
`--reload`, e vai bater nisso.

**Não corrigido nesta sessão**, por ser fora do escopo pedido (Seção 7 do `CLAUDE.md`). Fica como
pendência com prazo: precisa estar resolvido antes da Fase 9.

De quebra, o acidente virou a primeira verificação real do desenho de `/health`: com o Postgres
inacessível e o Redis de pé, a rota devolveu `503` mantendo o formato do corpo e truncou o detalhe
do erro na primeira linha, exatamente como projetado na sessão 1.

### Achado colateral: o `frontend/CLAUDE.md` volta sozinho

O `npm run dev` do Next 16 regenera `frontend/CLAUDE.md` e `frontend/AGENTS.md` a cada execução
(mensagem: *"Generated AGENTS.md and CLAUDE.md for AI agents. Set `agentRules: false` in
next.config to disable"*). A sessão 1 tinha apagado os dois por competirem com o arquivo de
contexto do projeto; apagar não resolve, é preciso desligar a flag. Removidos de novo e anotado.

### Verificação

| Comando | Resultado |
|---|---|
| `docker compose up -d` / `ps` | `verifyscan-postgres` e `verifyscan-redis` `Up (healthy)` |
| `uv sync` | 47 pacotes resolvidos, 46 conferidos |
| `uv run alembic upgrade head` | **falhou (exit 1)** → corrigido → `EXIT=0` |
| `Invoke-RestMethod .../health` | `status: ok`, Postgres 3,18 ms, Redis 0,88 ms |
| `npm install` | 359 pacotes, 0 vulnerabilidades |
| `npm run dev` | `Ready in 6.0s`, `GET / 200` |
| `uv run ruff format .` | 25 arquivos já formatados |
| `uv run ruff check .` | All checks passed |
| `uv run mypy app alembic` | Success: no issues found in 21 source files |
| `uv run pytest -q` | 4 passed |
| `npm run lint` | limpo |

**Gate 0 fechado.** A Fase 0 termina aqui.

### Pendências abertas

| Pendência | Natureza | Quando trava |
|---|---|---|
| **`--reload` mascara o event loop do Windows** | técnica — descoberta nesta sessão | **antes da Fase 9 (deploy)** |
| **`next.config` regenerando `CLAUDE.md`/`AGENTS.md`** | técnica — `agentRules: false` | qualquer hora; incomoda já |
| **Comitê de ética / consentimento** | externa — coordenação do curso | **bloqueante da Fase 2** |
| **3.9 — cronograma** | decisão do autor | atrasada: era da Fase 0 |
| **3.10 — deploy** | decisão do autor | Fase 9 |

A pendência 3.9 era para ter sido decidida na Fase 0 e a Fase 0 acabou. Continua sem decisão do
autor, e não será decidida por ele aqui.

### Próximo passo

Fase 1 do plano de execução: `POST /api/analises` com `TextAnalyzer`, `URLExtractor`,
`ScoringEngine` e `scoring/regras.yaml`, mais as telas de análise e resultado.

---

## 2026-08-28 — Sessão 3: o event loop do Windows como achado de plataforma

Duas correções antes da Fase 1. A primeira mudou de tamanho no meio do caminho e virou o
`ADR-0007`.

### 1. O bug do Proactor não era pendência de Fase 9 — era o backend não subindo

A sessão 2 tinha classificado "sem `--reload` o backend não fala com o Postgres" como pendência de
deploy. Classificação errada, e o motivo de estar errada é simples: `--reload` é modo de
desenvolvimento. Qualquer execução sem ele — teste de carga, demonstração para a banca, contêiner —
sobe um backend que responde `503` com `postgres: erro`. Corrigido nesta sessão.

**O que se pretendia fazer:** definir `asyncio.WindowsSelectorEventLoopPolicy()` na importação de
`app/main.py`, sob o mesmo guard `sys.platform == "win32"` do `alembic/env.py`.

**O que a medição mostrou:** isso **sozinho não funciona**. Com a política definida e sem
`--reload`, `/health` continuou devolvendo `503` com o mesmo `ProactorEventLoop`.

**Por quê.** O uvicorn não consulta a política de event loop do `asyncio`. Ele passa um
`loop_factory` explícito para o `asyncio.run` (`server.py:77` → `config.py:538`), e o
`asyncio.Runner` chama esse factory direto — a política nunca é lida. No Windows esse factory
devolve `ProactorEventLoop`, exceto quando a aplicação roda em subprocesso, que é justamente o
caso do `--reload`. Era por isso que o `--reload` "funcionava": por acidente, não por desenho.

**O que resolveu:** a política **mais** `--loop none` no comando. Com `--loop none`, o
`get_loop_factory()` do uvicorn devolve `None`, o `asyncio.run` cai no `new_event_loop()` e aí sim
a política é consultada. Os dois são necessários e cada um faz uma coisa: a política diz *qual*
loop; o `--loop none` faz o uvicorn *perguntar* em vez de impor o dele.

| Execução (sem `--reload`, Postgres e Redis reais) | `/health` |
|---|---|
| sem a política | 503 — `postgres: erro` |
| só a política em `main.py` | 503 — `postgres: erro` |
| política + `--loop none` | **200 — `status: ok`** |

Verificado no fim com o comando como ficou documentado, em porta limpa: PID 5008 rodando
`uvicorn app.main:app --port 8020 --loop none`, sem `--reload`, `/health` `status: ok` com
Postgres 51,78 ms e Redis 41,24 ms.

Decisão registrada no `ADR-0007`, incluindo as opções descartadas (driver síncrono só no Alembic;
entrypoint próprio `python -m app`). `README.md` e `CLAUDE.md` §3 passaram a documentar o comando
com `--loop none` e sem depender do `--reload`.

### Por que isto é material do capítulo de metodologia

O bug atravessou `ruff`, `mypy`, `pytest` e o CI **todos verdes**. Não foi descuido na revisão:
nenhum teste da suíte podia pegá-lo. A Seção 6 do `CLAUDE.md` proíbe teste que faça chamada de
rede, e o sintoma só existe contra um Postgres de verdade — em memória, o `httpx.AsyncClient` roda
sobre o loop que o `pytest-asyncio` cria, e nunca abre conexão.

É um **achado de plataforma**: não está no código do domínio, não está no RFC, e não é detectável
por análise estática nem por teste unitário. Ele vive na junção entre três decisões independentes —
async de ponta a ponta (ADR-0001), Windows como ambiente de desenvolvimento (`CLAUDE.md` §2) e um
servidor que escolhe o próprio event loop. Cada uma é defensável sozinha; o problema é a
combinação.

Duas consequências que valem para o resto do trabalho:

1. **Suíte verde não é evidência de sistema funcionando.** É evidência de que as unidades testáveis
   estão corretas. O que a suíte não toca precisa de um gate manual contra serviço real, e é por
   isso que o plano tem gates de infraestrutura em vez de só Definition of Done automatizado.
2. **A primeira classificação do achado estava errada** e ficou registrada assim na sessão 2
   ("pendência de Fase 9"). O erro foi supor que o modo de execução do desenvolvimento representa
   os outros. Vale como aviso para o resto do projeto: `--reload`, servidor de desenvolvimento do
   Next e fakes de rede escondem diferenças que só aparecem no modo real.

### 2. O `frontend/CLAUDE.md` regenerado

O Next 16 tem a flag: `agentRules: false` em `next.config.ts`. Aplicada com um comentário de duas
linhas dizendo por quê (um `CLAUDE.md` aninhado competiria com o da raiz). Verificado rodando
`npm run dev` de novo: a mensagem "Generated AGENTS.md and CLAUDE.md" sumiu e nenhum dos dois
arquivos voltou. Como a flag existe, não foi preciso mexer no `.gitignore`.

### Verificação

| Comando | Resultado |
|---|---|
| `uv run uvicorn app.main:app --port 8020 --loop none` (sem reload) | `/health` `status: ok` |
| `uv run ruff format .` | 25 arquivos já formatados |
| `uv run ruff check .` | All checks passed |
| `uv run mypy app alembic` | Success: no issues found in 21 source files |
| `uv run pytest -q` | 4 passed |
| `npm run lint` | limpo |
| `npx tsc --noEmit` | limpo |
| `npm run dev` | `Ready in 11.1s`, `GET / 200`, sem regenerar `CLAUDE.md` |

### Pendências abertas

| Pendência | Natureza | Quando trava |
|---|---|---|
| **Comitê de ética / consentimento** | externa — coordenação do curso | **bloqueante da Fase 2** |
| **3.9 — cronograma** | decisão do autor | atrasada: era da Fase 0 |
| **3.10 — deploy** | decisão do autor | Fase 9 |

As duas pendências técnicas abertas na sessão 2 foram fechadas aqui.

### Próximo passo

Fase 1 do plano de execução: `POST /api/analises` com `TextAnalyzer`, `URLExtractor`,
`ScoringEngine` e `scoring/regras.yaml`, mais as telas de análise e resultado.

---

## 2026-08-29 — Sessão 4: Fase 1, a fatia vertical de texto

**Gate 1 fechado.** Cola-se uma mensagem de golpe de PIX na tela e sai ALTO com os fatores, bem
abaixo de 1 segundo. Sem OCR, sem API externa, sem IA e sem login.

### O que foi feito

Sete commits, um por unidade lógica:

| Commit | Entrega |
|---|---|
| `feat(scoring)` | `regras.yaml` com as seis categorias e as faixas do RFC, validado por Pydantic no boot |
| `feat(analyzers)` | `TextAnalyzer` — as seis categorias da §5.4.1 |
| `feat(analyzers)` | `URLExtractor` — as quatro formas da §5.4.2 + forma canônica |
| `feat(scoring)` | `ScoringEngine` — agregação por categoria e classificação |
| `feat(api)` | `POST /api/analises` |
| `feat(frontend)` | telas de análise e resultado |
| `docs` | ADRs 0008, 0009 e 0010, errata item 8, emenda ao `CLAUDE.md` §6 |

Pesos confirmados por leitura direta do PDF (§5.4.1, p. 22–23): urgência +10, personificação de
marca +15, ameaça/bloqueio +15, prêmio falso +20, solicitação financeira +25, dados pessoais +25.
Teto de texto puro: **110**. Faixas 0–30 / 31–60 / 61+ conferem com a §5.4.7 (p. 26).

### Três decisões do Walter que mudaram o plano que eu tinha proposto

Registradas porque o raciocínio delas é material de capítulo, não porque a decisão mudou.

**1. `urls_analisadas` entra no contrato agora.** Eu havia proposto deixar os links fora da
resposta na Fase 1, já que nada pontua em cima deles até a Fase 3. O argumento contra: acrescentar
campo na Fase 3 é mudança de contrato, que é exatamente o que a instrução das flags de degradação
existe para evitar. O argumento sobre a *tela* estava certo (o campo não é exibido); sobre o
*contrato*, errado. São duas perguntas diferentes e eu as tinha juntado numa só.

**2. Texto acima do limite é recusado, nunca truncado.** Eu tinha escrito "limite de 5.000
caracteres" sem dizer o que acontece ao ultrapassá-lo — ambiguidade que a implementação resolveria
sozinha, provavelmente truncando. Truncar significaria pontuar sobre conteúdo parcial: um pedido
de PIX no fim de uma mensagem longa sumiria e a resposta viria BAIXO. **Falso negativo causado por
detalhe de implementação é o pior tipo** — o sistema erra e parece confiante. O limite virou
configuração (`TEXTO_MAX_CARACTERES`) para a Fase 2 poder ajustá-lo contra o corpus. Há dois
testes para isso, e o segundo existe só para nomear o motivo.

**3. O enum de `IndicadorRisco.tipo` diverge do RFC — e eu não sinalizei.** Propus
`(texto, dominio, reputacao)` no lugar de `(url, texto, dominio, ocr, email)` da §5.5 tratando
como detalhe de implementação. Não é: é o enum que vira coluna na Fase 8. Virou o **item 8 da
errata**, com a justificativa de que `url` funde duas coisas que falham por motivos diferentes
(domínio não degrada, reputação degrada com a cota da VirusTotal) e `ocr` é origem da entrada, não
tipo de indicador — informação que `Analise.tipo_input` já carrega. Decidir na Fase 1 evita
migração retroativa na Fase 8.

*O padrão nos três: eu tratei como detalhe de implementação três coisas que eram decisão de
contrato.* Vale como aviso para as fases seguintes.

### O falso positivo conhecido virou teste

O achado 1 do `analise-rfc-v1.1.md` diz que o SMS legítimo "Banco do Brasil informa: sua conta
será suspensa. Clique agora para regularizar" soma 15+15+10 = **40** e cai em MÉDIO — que conta
como golpe na métrica (ADR-0005) — sem nenhum indicador de fraude.

O pedido da sessão incluía "um teste com uma mensagem legítima de banco que não pode ser
classificada como golpe". Escrito com *essa* mensagem, o teste falharia por construção: o conserto
é a calibração da Fase 2, não código da Fase 1. Resolvido com dois testes:

- uma mensagem legítima que de fato não dispara padrão nenhum (fatura, compra aprovada, boleto de
  condomínio, aviso antifraude do próprio banco) → 0 fatores;
- o SMS do achado 1 como `xfail(strict=True)`, citando o achado. Ele documenta a pendência dentro
  da suíte, e o `strict` **avisa quando a Fase 2 a fechar** — se um dia passar, o teste quebra.

### Decisões técnicas que viraram ADR

- **ADR-0008** — formato do `regras.yaml`. O ponto não óbvio: o mesmo normalizador roda no texto e
  no padrão, o que permite escrever `'últimas horas'` no YAML. Como ele faz `.lower()`, uma classe
  de regex maiúscula (`\D`, `\S`, `\W`, `\B`) viraria a minúscula — a regex continuaria compilando
  e passaria a significar **o oposto**. O carregamento recusa, com mensagem explícita. Descoberto
  escrevendo o ADR, não depurando; teria sido um bug muito caro de achar.
- **ADR-0009** — forma canônica de URL. A decisão que importa: descartar o `usuario@`.
  `http://bradesco.com.br@golpe.xyz` tem host real `golpe.xyz`; preservar a forma digitada faria a
  Fase 3 medir Levenshtein contra o domínio errado e responder "parece legítimo" para um phishing
  clássico.
- **ADR-0010** — interface. Reconcilia a "Tela 2" do mockup: estado único na Fase 1 (a análise
  leva <1 s), etapas de volta na Fase 5 em vocabulário do usuário ("Lendo a imagem…"), e a barra
  de progresso percentual **não volta em nenhuma fase** — o pipeline não sabe quanto falta, e
  qualquer porcentagem seria animação arbitrária.

### Desvio deliberado do RFC no `regras.yaml`

A §5.4.1 dá "dados bancários" como exemplo de padrão da categoria de dados pessoais. Solto, ele
casa com o aviso antifraude legítimo do próprio banco — "nunca pedimos seus dados bancários por
SMS" — que é um falso positivo particularmente ruim: a mensagem que o produto classificaria como
golpe é a que ensina a pessoa a não cair em golpe. O padrão passou a exigir verbo
(`informe|confirme|digite|envie|atualize|valide|cadastre`). Está coberto por teste nomeado.

### Verificação

| Comando | Resultado |
|---|---|
| `uv run ruff format .` / `ruff check .` | All checks passed |
| `uv run mypy app` | Success: no issues found in 29 source files |
| `uv run pytest -q` | **87 passed, 1 xfailed** |
| `npm run lint` / `npx tsc --noEmit` | limpo |
| `npm run build` | compilado, rotas `/` e `/status` |
| `POST /api/analises` contra o servidor real | score **75**, `ALTO`, 4 fatores, `urls_analisadas: ["http://bb-regularize.xyz/"]`, ambas as flags `false` |

Susto de leitura durante a verificação: a resposta apareceu como `vocÃª` no terminal. Não era
mojibake — `python -m json.tool` lê stdin em cp1252 no Windows. Conferido nos codepoints:
`U+00EA`, correto. **Vale a lição para a Fase 2:** a máquina de medição pode mentir sobre o dado
antes que o dado esteja errado; verificar o codepoint custa uma linha e evita "consertar" o que
não está quebrado.

### Pendências abertas

| Pendência | Natureza | Quando trava |
|---|---|---|
| **Comitê de ética / consentimento** | externa — coordenação do curso | **bloqueante da Fase 2** |
| **Corte do `EmailAnalyzer`** | decisão do autor, a formalizar | antes da Fase 2 |
| **3.9 — cronograma** | decisão do autor | atrasada desde a Fase 0 |
| **3.10 — deploy** | decisão do autor | Fase 9 |

Nenhum teste automatizado de frontend: a Fase 1 verifica com `lint`, `tsc`, `build` e olho. A
revisão de acessibilidade com leitor de tela e teclado é entrega da Fase 9, e é conteúdo de
capítulo — não polimento.

### Próximo passo

Fase 2: corpus rotulado (mínimo 150 casos, 60 negativos), `tools/avaliar_corpus.py`, baseline
trivial e a primeira rodada de calibração de pesos **e faixas**. É onde o `xfail` acima deve
fechar. Bloqueada pelo comitê de ética.
