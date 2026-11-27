# VerifyScan

[![Quality Gate](https://sonarcloud.io/api/project_badges/measure?project=WalterTheodoro_VerifyScan&metric=alert_status)](https://sonarcloud.io/summary/overall?id=WalterTheodoro_VerifyScan)
[![Cobertura](https://sonarcloud.io/api/project_badges/measure?project=WalterTheodoro_VerifyScan&metric=coverage)](https://sonarcloud.io/summary/overall?id=WalterTheodoro_VerifyScan)

Plataforma web que recebe uma mensagem suspeita — texto, link, print ou e-mail — e devolve
**nível de risco (BAIXO / MÉDIO / ALTO), os fatores identificados e uma recomendação**, em
português acessível a quem tem pouco letramento digital.

O coração do produto é um pipeline heurístico próprio. A IA **não decide risco sozinha**: ela
lê a mensagem, sugere um nível e explica o que a mensagem parece ser e o que fazer, e uma regra
fixa deixa o nível final no maior dos dois — a IA pode subir o nível, nunca baixar (ADR-0020).

TCC de Engenharia de Software — Católica SC. Especificação em `docs/RFC-VerifyScan-v1.1.pdf`,
plano de execução em `docs/plano-de-execucao.md`, decisões em `docs/adr/`.

> **Estado atual: fatia 9 (análise de print).** Você cola uma mensagem e recebe o nível de
> risco, o que ela parece ser, o que fazer e os sinais encontrados. Depois das regras, uma chamada
> ao Claude Haiku 5.5 lê a mensagem e pode subir o nível, nunca baixar; sem a IA, a resposta é a das
> regras, com a orientação fixa do nível (ADR-0020). Sem conta, a análise fica no banco sem o texto.
> Com conta, ela vai para o histórico por 7 dias, com a mensagem e a mesma resposta da tela
> (ADR-0018), e em "Minha conta" dá para apagar análises, trocar a senha e excluir a conta
> (ADR-0019). Desde a fatia 8, os links também pontuam, só pelo texto do endereço: o sistema
> **nunca abre o link**, e a tela mostra só o domínio e o que se achou dele, nunca o link inteiro
> (ADR-0022). Desde a fatia 9, dá para enviar um **print** da conversa (botão, Ctrl+V ou arrastar):
> o Claude lê o texto e o que a tela mostra (contato salvo, aviso do aplicativo, primeira
> mensagem), e a transcrição passa pelo mesmo caminho do texto. A imagem sai do navegador reduzida
> e sem metadados e nunca é guardada; com conta, fica só o texto lido (ADR-0023). Ainda sem
> consulta a APIs externas de reputação (Fase 4).

---

## Pré-requisitos (Windows)

O ambiente de desenvolvimento é Windows e todos os comandos abaixo são de PowerShell. Não há
`Makefile` neste projeto.

| Ferramenta | Versão | Como instalar |
|---|---|---|
| Git | qualquer recente | `winget install Git.Git` |
| Docker Desktop | 4.x | `winget install Docker.DockerDesktop` — **exige reiniciar a máquina** |
| Python | 3.12 | o `uv` baixa sozinho; não precisa instalar |
| uv | 0.5+ | `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"` |
| Node.js | 22 LTS ou superior | `winget install OpenJS.NodeJS.LTS` |

Depois de instalar qualquer coisa por `winget`, **feche e reabra o PowerShell** — o `PATH` só é
relido em terminal novo.

Confira:

```powershell
git --version
docker --version
uv --version
node --version
```

O print é lido pelo Claude, não por OCR local (ADR-0023): não há Tesseract para instalar. As
ferramentas que desenham prints sintéticos usam o Microsoft Edge que já vem no Windows.

---

## Setup

### 1. Clonar e configurar as variáveis de ambiente

```powershell
git clone <url-do-repositorio> VerifyScan
Set-Location VerifyScan
Copy-Item .env.example .env
```

Abra o `.env` e preencha, no mínimo, o que a Fase 0 usa:

- `POSTGRES_PASSWORD` — escolha qualquer senha para o banco local. O `docker compose` **recusa a
  subir** se ela estiver vazia, de propósito.
- `DATABASE_URL` — troque `SENHA_AQUI` pela mesma senha.

O `.env` nunca é versionado. Todas as demais variáveis estão comentadas por fase no
`.env.example` e só passam a ser lidas quando a fase correspondente chegar.

Para a análise com IA (ADR-0020), preencha também `ANTHROPIC_API_KEY` e ponha `IA_ATIVADA=true`.
Sem isso, tudo funciona com as regras sozinhas. Com `IA_ATIVADA=true` e sem a chave, o backend
não sobe, e o erro diz qual variável falta.

### 2. Subir Postgres e Redis

Com o Docker Desktop **aberto e rodando**:

```powershell
docker compose up -d
docker compose ps
```

Espere `STATUS` chegar a `healthy` nos dois containers — leva uns 10 segundos. Se ficar em
`starting` para sempre, veja `docker compose logs postgres`.

### 3. Backend

```powershell
Set-Location backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --port 8000 --loop none --reload
```

O `uv sync` cria o `.venv` e instala tudo a partir do `uv.lock` — não é preciso ativar o ambiente
virtual: `uv run` já faz isso.

Antes do `alembic upgrade`, o `.env` precisa de `IP_HMAC_SEGREDO` e `PROXY_SEGREDO` (ADR-0024),
com pelo menos 32 caracteres cada. Eles não têm default: sem eles, nem o Alembic nem o uvicorn
sobem, e o erro diz qual falta. Gere cada um com
`uv run python -c "import secrets; print(secrets.token_urlsafe(48))"`.

O `alembic upgrade head` aplica as migrações que faltam no banco do `docker compose`. Rode-o
depois de todo `docker compose up` com volume novo e sempre que puxar uma migração nova — o
esquema só muda por migração, nunca à mão.

O `--loop none` **não é opcional no Windows** e não tem nada a ver com o `--reload`. Ele é o que
faz o uvicorn usar o event loop que a aplicação escolhe, em vez de impor o dele: sem ele, o
processo nasce com o `ProactorEventLoop`, o `psycopg` se recusa a rodar nesse loop e `/health`
responde `503` com `postgres: erro`. Detalhe e medição no `docs/adr/ADR-0007`. O `--reload` é só
conveniência de desenvolvimento — tire-o para rodar como em produção, mas mantenha o `--loop none`.

Em **outra janela** do PowerShell, confira a saúde:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Resposta esperada:

```
status   : ok
postgres : @{status=ok; latencia_ms=3.1; detalhe=}
redis    : @{status=ok; latencia_ms=1.4; detalhe=}
```

A rota devolve **HTTP 503** e `status: degradado` se qualquer serviço estiver fora, mantendo o
mesmo formato de corpo. Documentação interativa da API em <http://localhost:8000/docs>.

### 4. Frontend

Em outra janela, a partir da raiz do repositório:

```powershell
Set-Location frontend
Copy-Item .env.local.example .env.local
npm install
npm run dev
```

Abra <http://localhost:3000> e cole uma mensagem suspeita para analisar.

O navegador nunca chama o backend direto: o Next repassa `/api/*` e `/health` para
`API_URL_INTERNA` (default `http://localhost:8000` fora de produção; ADR-0014). Um
`npm run build` exige a variável no `.env.local` — sem ela, o build falha de propósito.

No caminho, o `proxy.ts` repassa ao backend o IP do visitante, com o segredo compartilhado
(ADR-0024). Para isso, `PROXY_SEGREDO` no `.env.local` precisa ter o mesmo valor do `.env` do
backend. No `npm run dev` ele é opcional: sem ele, o backend vê o IP do Next. O `npm run build`
exige a variável.

Em <http://localhost:3000/status> fica a página de infraestrutura, que consulta `/health` e
mostra o estado de Postgres e Redis separadamente.

---

## Comandos do dia a dia

### Qualidade — rodar sempre antes de commitar

```powershell
Set-Location backend
uv run ruff format .
uv run ruff check . --fix
uv run mypy app
uv run pytest -q
```

```powershell
Set-Location frontend
npm run lint
npm test
```

Se mexeu em `infra/vm/` (os scripts que rodam na VM de produção), de dentro de `backend`:

```powershell
uv run ruff format ../infra
uv run ruff check ../infra
uv run mypy --strict --platform linux --explicit-package-bases ../infra/vm
uv run pytest ../infra -q -p no:cacheprovider
```

O CI roda exatamente isso a cada push (`.github/workflows/ci.yml`), com `ruff format --check` no
lugar do `ruff format`, mais `alembic upgrade head` e `alembic check` contra um Postgres de teste,
e com a cobertura ligada nos dois lados (seção seguinte). Roda também a pilha de produção inteira
com um teste da cadeia de IP da cota, e confere que o Bicep compila (ADR-0029).

### Cobertura de testes

Dois relatórios, um comando cada. O do backend mede `app/` inteiro; o do frontend, `app/` e os três
arquivos de código da raiz (`proxy.ts`, `instrumentation.ts`, `instrumentation-client.ts`), sem
testes nem configuração (ADR-0027). Os dois contam os arquivos
que nenhum teste importa, e saem com erro abaixo da meta (ADR-0025).

| | Backend | Frontend |
|---|---|---|
| Pasta | `backend` | `frontend` |
| Comando | `uv run pytest -q --cov=app --cov-report=term-missing` | `npm test` |
| Meta | **75%** | **25%** de linhas |
| Onde a meta está | `fail_under` em `[tool.coverage.report]`, no `pyproject.toml` | `coverage.thresholds.lines`, no `vitest.config.ts` |
| Relatório | tabela por arquivo no terminal | tabela por arquivo no terminal, `coverage/index.html` e `coverage/coverage-summary.json` |
| Medido em 22/11/2026 | 92,41%, só unitários (866 testes) | 52,01% de linhas (158 testes) |

```powershell
Set-Location backend
uv run pytest -q --cov=app --cov-report=term-missing
```

```powershell
Set-Location frontend
npm test
```

- **Backend e o Postgres de teste:** se o `.env` tem `TEST_DATABASE_URL`, o comando roda também os
  testes de integração e precisa do `docker compose up -d`. Com o Postgres fora do ar eles não são
  pulados: cada um espera a conexão falhar, e a execução demora e termina em erro. Sem o Docker,
  meça só os unitários:

  ```powershell
  uv run pytest -q -m "not integracao" --cov=app --cov-report=term-missing
  ```

  O número acima é o deste comando. Com a integração, a cobertura só sobe (os repositórios, que
  falam com o banco, são o que os unitários não alcançam).
- **A cobertura do backend não liga sozinha:** o `uv run pytest -q` do dia a dia segue sem ela, que
  deixa a suíte uns 28% mais lenta. Só o CI e o comando acima a usam.
- **Frontend:** `npm test` sempre mede. A pasta `frontend/coverage/` é ignorada pelo git.

### Análise estática

O SonarQube Cloud analisa o backend, o frontend e os workflows do CI (ADR-0027). Não há comando
local: quem roda é o job `sonar` do CI, depois dos testes, com a cobertura que os outros dois jobs
geraram (`backend/coverage.xml` e `frontend/coverage/lcov.info`).

- **Painel:** <https://sonarcloud.io/project/overview?id=WalterTheodoro_VerifyScan>
- **O que entra, o que é teste e o que foi aceito:** `sonar-project.properties`, na raiz. Cada
  questão ignorada está lá com o motivo; a triagem inteira está no ADR-0027.
- **O Quality Gate ainda não bloqueia o merge.** O selo acima mostra o estado, mas o CI não
  reprova por ele.
- **O selo de cobertura não é nenhum dos dois números da seção anterior.** Ele mostra um número
  só, do projeto inteiro: backend e frontend somados, com linhas e ramos na mesma conta. Os
  arquivos medidos são os mesmos do pytest-cov e do Vitest; a conta é que é outra. No frontend o
  Sonar também fica uns 3 pontos abaixo do Vitest, porque soma às linhas a cobrir as que só têm
  dado de ramo. Para a prova de autoria valem os dois comandos da seção anterior.
- **PR de fork:** o job é pulado, porque o fork não recebe o `SONAR_TOKEN`.

### Banco de teste (testes de integração)

Os testes marcados `integracao` falam com um Postgres **de teste** — nunca com o de produção. Sem
`TEST_DATABASE_URL` eles são pulados e o resto da suíte roda normalmente.

Crie o banco uma vez, com o `docker compose` de pé:

```powershell
docker compose exec postgres createdb -U verifyscan verifyscan_teste
```

Depois aponte `TEST_DATABASE_URL` no `.env` para ele — igual à `DATABASE_URL`, trocando o nome do
banco para `verifyscan_teste`. O nome **precisa** terminar em `_teste`: a sessão de testes refaz o
esquema do zero pelo Alembic (`downgrade base` → `upgrade head`) e recusa qualquer outro banco.

```powershell
uv run pytest -q -m integracao        # só integração
uv run pytest -q -m "not integracao"  # só unitários, sem banco
```

### Avaliação contra o corpus rotulado

```powershell
Set-Location backend
uv run python -m tools.avaliar_corpus                            # motor, offline, calibração e teste
uv run python -m tools.avaliar_corpus --com-ia --divisao teste   # motor + IA real (fora do CI)
uv run python -m tools.avaliar_corpus --gravar-linha-de-base     # regrava o gate do CI
uv run python -m tools.sortear_divisao                           # divide só os casos novos
```

Mede o motor (e, com `--com-ia`, o motor com a IA) nos casos de `corpus/casos/`. O resultado sai
por divisão, no total e por autor:
- a matriz de níveis;
- golpes detectados e alarmes falsos;
- precisão, recall, F1 e acurácia, com o intervalo de 95% de Wilson;
- o KPI do §1.6 (precisão e recall acima de 85%, errata 14);
- a comparação com uma linha de base trivial.

Cada rodada escreve um relatório novo em `docs/avaliacoes/`. Ele leva o carimbo das regras, do
modelo, do commit, do hash do corpus e da semente, e lista os erros só pelo id do caso.

O `pytest` roda o motor na calibração e falha se ele piorar mais de um caso em relação à
`tools/linha_de_base_motor.json`. O `--com-ia` usa a chave do `.env` e custa uns 2 centavos de
dólar por rodada no teste. Decisões e limitações: ADR-0021.

### Análise com IA contra a API real (fora do CI)

```powershell
Set-Location backend
uv run python -m tools.testar_ia
```

Roda as 26 mensagens sintéticas de `tools/amostras_ia.yaml` contra a Anthropic, com a chave do
`.env`, mesmo com `IA_ATIVADA=false`, e imprime motor, IA, nível final, tipo, latência e plano B.
Custa centavos de dólar e **não substitui o corpus** da Fase 2. Os testes (`pytest`) nunca chamam
a API: usam um cliente falso.

### Prints sintéticos (fora do CI)

```powershell
Set-Location backend
uv run python -m tools.gerar_prints                    # desenha os 45 prints da calibração
uv run python -m tools.avaliar_prints                  # mede a leitura e a análise (API real)
uv run python -m tools.gerar_prints --divisao teste    # a medida limpa: só uma vez, no fim
uv run python -m tools.avaliar_prints --divisao teste
```

O `gerar_prints` desenha conversas **genéricas** (nada que imite a marca de um aplicativo) a partir
de casos do corpus, com variações de contexto. Os PNGs vão para `corpus/prints-gerados/`, que o git
ignora; só a lista de ids e variações (`tools/prints_sinteticos.yaml`) é versionada. O
`avaliar_prints` mede a taxa de erro por caractere da transcrição, o acerto de cada campo do
contexto, o nível do print contra o do texto do mesmo caso, o plano B dos borrados, a latência e o
custo, e escreve o relatório em `docs/avaliacoes/`. Custa uns 6 centavos de dólar por rodada. Os
prints são limpos demais: a taxa de erro medida é otimista (ADR-0023).

### Observabilidade

Logs em JSON com o id de cada requisição, métricas em `GET /metrics` (com `METRICS_TOKEN`) e
erros no Sentry (só com `SENTRY_DSN` e `NEXT_PUBLIC_SENTRY_DSN`). Nenhum dos três leva o conteúdo
da mensagem nem dado de quem usa: só tipo, nível, duração, status e motivo.

Como ver os logs, consultar as métricas, achar um erro e a lista de eventos e métricas:
[`docs/observabilidade.md`](docs/observabilidade.md). As decisões estão no
[ADR-0026](docs/adr/ADR-0026-observabilidade.md).

### Infraestrutura local

```powershell
docker compose up -d      # sobe Postgres e Redis
docker compose ps         # estado e healthcheck
docker compose logs -f    # acompanha os logs
docker compose down       # para tudo, preservando os dados
docker compose down -v    # apaga os volumes junto (banco zerado)
```

---

## Estrutura

```
VerifyScan/
├─ backend/            FastAPI + SQLAlchemy async + Alembic
│  ├─ app/
│  │  ├─ api/          rotas finas: validam, chamam um service, devolvem schema
│  │  ├─ services/     a regra fica aqui
│  │  ├─ analyzers/    TextAnalyzer, URLExtractor, DomainAnalyzer, EmailAnalyzer (Fases 1, 3, 6)
│  │  ├─ ocr/          o print: validação e reencode com Pillow, e a leitura pelo Claude (Fase 5)
│  │  ├─ reputation/   URLChecker e provedores externos (Fase 4)
│  │  ├─ scoring/      ScoringEngine, regras.yaml, respostas.yaml (plano B) e a combinação
│  │  ├─ formulator/   análise com o Claude: cliente, prompt, saída e limpeza (ADR-0020)
│  │  ├─ models/       SQLAlchemy: Analise, IndicadorRisco, Usuario, SessaoUsuario (Fase 8)
│  │  ├─ schemas/      Pydantic — o contrato da API
│  │  └─ core/         config, banco, cache, hash de senha, timeouts
│  ├─ alembic/         migrações — o esquema só muda por elas
│  ├─ tools/           scripts: avaliar_corpus e sortear_divisao (Fase 2), testar_ia e amostras_ia.yaml,
│  │                   gerar_prints e avaliar_prints (Fase 5)
│  └─ tests/          unitários sem rede; integracao/ fala com o Postgres de teste
├─ frontend/           Next.js App Router + TypeScript + Tailwind
├─ infra/              a produção na Azure: Bicep, compose.yml, Caddyfile e os scripts da VM (ADR-0029)
├─ .github/workflows/  ci.yml (testes e análise) e deploy.yml (publica a master na VM)
├─ corpus/             176 casos sintéticos rotulados, divisão fixa calibração/teste (Fase 2)
├─ docs/               RFC, plano de execução, ADRs, diário de bordo, deploy.md e avaliacoes/ (relatórios)
└─ docker-compose.yml  Postgres 16 e Redis 7, só para o desenvolvimento
```

---

## Produção

Uma VM na Azure, no Chile, com Docker Compose: Caddy (HTTPS automático), frontend, backend e
Postgres 16 ([ADR-0029](docs/adr/ADR-0029-hospedagem-na-azure.md)). Só as portas 80 e 443 são
abertas; não há SSH. Até 27/11/2026 a produção ficava no Render, com o banco no Neon; os dados
vieram de lá nesse dia.

- **Endereço:** <https://verifyscan.chilecentral.cloudapp.azure.com>
- **Deploy:** sozinho, depois do CI verde na `master` (`.github/workflows/deploy.yml`). Se a versão
  nova não responder, a VM volta para a anterior.
- **Segredos:** num cofre da Azure, lidos pela VM a cada deploy. Não há `.env` em produção.
- **Backup:** todo dia às 03:00 de Brasília, guardado por 7 dias.
- **Infraestrutura:** em `infra/`, como código (Bicep).

Como publicar, voltar uma versão, ver os logs, restaurar um backup e migrar os dados:
[`docs/deploy.md`](docs/deploy.md).

**Toda migração precisa ser aditiva**: a volta de versão não desfaz migração. Remover ou renomear
coluna leva dois deploys.

### Configuração

Os segredos vêm do cofre, e o resto está escrito em `infra/compose.yml`. O que esse arquivo não
define fica no default do `Settings`, que já é o de produção: cotas, teto de gasto, tempos
limite, sessão e histórico de 7 dias. As variáveis e o limite de cada uma estão comentados no
`.env.example`.

Para mudar um desses valores (subir `IA_COTA_SEM_CONTA` no Demo Day, em que todo mundo sai pelo
mesmo IP, por exemplo), acrescente a variável ao serviço `backend` do `infra/compose.yml` e
publique: ela vale a partir do deploy seguinte. Desligar a IA é no mesmo arquivo, trocando
`IA_ATIVADA` para `"false"`.

A reputação de links (ADR-0028) só funciona com `SAFE-BROWSING-API-KEY` e `VIRUSTOTAL-API-KEY`
preenchidos no cofre. Sem uma delas, aquela base não é consultada, e a análise com link avisa que
a verificação externa não foi possível.

---

## Problemas comuns

**`docker compose up` falha com `defina POSTGRES_PASSWORD no .env`.**
É o comportamento pretendido: você copiou o `.env.example` mas não preencheu a senha.

**`Invoke-RestMethod` responde 503 com `postgres: erro`.**
Os containers não estão de pé ou ainda não ficaram `healthy`. Rode `docker compose ps`. Se
estiverem OK, confira se `DATABASE_URL` no `.env` usa a mesma senha de `POSTGRES_PASSWORD` e a
porta de `POSTGRES_PORT`.

**A porta 5432 já está em uso.**
Existe um Postgres instalado direto no Windows. Mude `POSTGRES_PORT` no `.env` (por exemplo,
`5433`), ajuste a porta dentro de `DATABASE_URL` também, e suba de novo.

**O `/status` mostra "Não conseguimos falar com o servidor."**
O backend não está no ar, ou está em outra porta. Suba com
`uv run uvicorn app.main:app --port 8000 --loop none` (o `--loop none` é do Windows, ADR-0007) e
confira o valor de `API_URL_INTERNA` em `frontend/.env.local`. Mudança nessa variável exige
reiniciar o `npm run dev` — e, no build de produção, rodar o `npm run build` de novo: as rewrites
ficam gravadas no build.

**Em produção, a tela mostra "O servidor está acordando".**
Na VM o backend não dorme (ADR-0029): essa tela quer dizer que ele não está respondendo. Durante
um deploy isso dura alguns segundos, e a tela tenta de novo sozinha por até 90 s (ADR-0017). Se
não passar, veja "Problemas comuns" em [`docs/deploy.md`](docs/deploy.md).

**`uv sync` reclama que o `uv.lock` está desatualizado.**
Alguém mexeu no `pyproject.toml`. Rode `uv lock` e commite o `uv.lock` junto.
