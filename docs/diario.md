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
