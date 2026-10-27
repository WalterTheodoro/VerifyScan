# VerifyScan

Plataforma web que recebe uma mensagem suspeita — texto, link, print ou e-mail — e devolve
**nível de risco (BAIXO / MÉDIO / ALTO), os fatores identificados e uma recomendação**, em
português acessível a quem tem pouco letramento digital.

O coração do produto é um pipeline heurístico próprio. A IA **não decide risco sozinha**: ela
lê a mensagem, sugere um nível e explica o que a mensagem parece ser e o que fazer, e uma regra
fixa deixa o nível final no maior dos dois — a IA pode subir o nível, nunca baixar (ADR-0020).

TCC de Engenharia de Software — Católica SC. Especificação em `docs/RFC-VerifyScan-v1.1.pdf`,
plano de execução em `docs/plano-de-execucao.md`, decisões em `docs/adr/`.

> **Estado atual: fatia 6 (análise com o Claude).** Você cola uma mensagem e recebe o nível de
> risco, o que ela parece ser, o que fazer e os sinais encontrados. Depois das regras, uma chamada
> ao Claude Haiku 5.5 lê a mensagem e pode subir o nível, nunca baixar; sem a IA, a resposta é a das
> regras, com a orientação fixa do nível (ADR-0020). Sem conta, a análise fica no banco sem o texto.
> Com conta, ela vai para o histórico por 7 dias, com a mensagem e a mesma resposta da tela
> (ADR-0018), e em "Minha conta" dá para apagar análises, trocar a senha e excluir a conta
> (ADR-0019). Desde a fatia 8, os links também pontuam, só pelo texto do endereço: o sistema
> **nunca abre o link**, e a tela mostra só o domínio e o que se achou dele, nunca o link inteiro
> (ADR-0022). Ainda sem OCR e sem consulta a APIs externas de reputação (Fases 4 e 5).

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
| Tesseract OCR | 5.x, com idioma `por` | ver a seção abaixo |

Depois de instalar qualquer coisa por `winget`, **feche e reabra o PowerShell** — o `PATH` só é
relido em terminal novo.

Confira:

```powershell
git --version
docker --version
uv --version
node --version
```

### Tesseract com o pacote de idioma português

O Tesseract **não vem pelo `pip`** — o `pytesseract` é só um invólucro que chama o binário. Ele só
é usado a partir da Fase 5, mas instale agora: é o passo que mais trava quem tenta rodar o projeto.

1. Baixe o instalador do build do UB Mannheim:
   <https://github.com/UB-Mannheim/tesseract/wiki> (arquivo `tesseract-ocr-w64-setup-*.exe`).
2. Durante a instalação, abra **Additional language data** e **marque `Portuguese`**. Se pular esta
   tela, o OCR instala só com inglês e o resultado em mensagens em português fica inutilizável.
3. Anote o caminho de instalação — o padrão é `C:\Program Files\Tesseract-OCR`.
4. Confirme que o idioma foi instalado (a lista precisa conter `por`):

   ```powershell
   & "C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs
   ```

5. Aponte `TESSERACT_CMD` no `.env` para o executável. O `pytesseract` não descobre o caminho
   sozinho no Windows.

Se esqueceu de marcar o idioma, rode o instalador de novo e escolha *Modify*.

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
```

O CI roda exatamente isso a cada push (`.github/workflows/ci.yml`), com `ruff format --check` no
lugar do `ruff format`, mais `alembic upgrade head` e `alembic check` contra um Postgres de teste.

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

### Infraestrutura

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
│  │  ├─ ocr/          OCRProcessor (Fase 5)
│  │  ├─ reputation/   URLChecker e provedores externos (Fase 4)
│  │  ├─ scoring/      ScoringEngine, regras.yaml, respostas.yaml (plano B) e a combinação
│  │  ├─ formulator/   análise com o Claude: cliente, prompt, saída e limpeza (ADR-0020)
│  │  ├─ models/       SQLAlchemy: Analise, IndicadorRisco, Usuario, SessaoUsuario (Fase 8)
│  │  ├─ schemas/      Pydantic — o contrato da API
│  │  └─ core/         config, banco, cache, hash de senha, timeouts
│  ├─ alembic/         migrações — o esquema só muda por elas
│  ├─ tools/           scripts: avaliar_corpus e sortear_divisao (Fase 2), testar_ia e amostras_ia.yaml
│  └─ tests/          unitários sem rede; integracao/ fala com o Postgres de teste
├─ frontend/           Next.js App Router + TypeScript + Tailwind
├─ corpus/             176 casos sintéticos rotulados, divisão fixa calibração/teste (Fase 2)
├─ docs/               RFC, plano de execução, ADRs, diário de bordo e avaliacoes/ (relatórios)
└─ docker-compose.yml  Postgres 16 e Redis 7
```

---

## Produção

Backend no plano gratuito do Render; banco no Neon gratuito (decisão e custos no
`docs/adr/ADR-0011`). Estes passos são manuais, feitos uma vez, nos painéis:

1. **Criar o projeto no Neon** na região **AWS us-west-2** (a mesma do Render em Oregon), com
   **Postgres 16** — igual ao `docker compose` e ao CI.
2. **Copiar a connection string com "Connection pooling" DESLIGADO.** O host não pode ter
   `-pooler`: a API é um processo de longa duração com pool próprio, e a migração precisa da
   conexão direta. Cole como vem (`postgresql://...?sslmode=require&channel_binding=require`) — a
   aplicação troca o dialeto para `postgresql+psycopg://` sozinha.
3. **No Render, colocar essa string em `DATABASE_URL`.** A mesma variável serve à API e ao Alembic.
4. **Trocar o build command do Render** para:

   ```
   pip install uv && uv sync --frozen && uv run --frozen alembic upgrade head
   ```

   A migração roda no build porque o *pre-deploy command* do Render é só dos planos pagos. Por
   isso toda migração precisa ser aditiva; remover ou renomear coluna leva dois deploys.
5. **Deixar `REDIS_URL` sem valor.** O Redis fica desativado até a Fase 4, e o `/health` responde
   `redis: desativado` com status `ok`.
6. **Autenticação (ADR-0013): nada a definir.** Os defaults já são os de produção:
   `COOKIE_SECURE=true` (não precisa ser definida — e nunca deve ir como `false` no Render),
   `SESSAO_DIAS=7` e `TIMEOUT_AUTENTICACAO_S=5`. As variáveis `JWT_*` que existiam no
   `.env.example` saíram: a sessão é opaca, em banco, e não há segredo de assinatura. Se elas
   estiverem no painel do Render, podem ser apagadas.
   O histórico (ADR-0015) também já vem no default de produção: `HISTORICO_DIAS=7`, por quantos
   dias a análise feita logado fica ligada à conta, com a mensagem (ADR-0018). As migrações
   `0003` a `0005` rodam sozinhas no build. `TEXTO_MAX_CARACTERES` não pode passar de 5000: o
   CHECK da `0004` limita o texto guardado, e o backend não sobe com valor maior.
7. **Análise com IA (ADR-0020).** No serviço **VerifyScan** (o backend) → **Environment**:
   - `IA_ATIVADA=true` — liga a chamada ao Claude. Sem ela (ou com `false`), a análise sai só com
     as regras, e é assim que se desliga a IA sem novo deploy de código;
   - `ANTHROPIC_API_KEY` — a chave da API, **como segredo** (o Render não a mostra depois de
     salva). Obrigatória com a IA ligada: sem ela, o backend não sobe;
   - opcionais, com estes defaults: `IA_MODELO=claude-haiku-5-5`, `IA_TIMEOUT_S=15` (máximo 15 —
     o backend não sobe com mais), `IA_MAX_TOKENS=700`;
   - `LOG_LEVEL=INFO` já é o default: é ele que mostra, nos logs do Render, a latência e os tokens
     de cada análise com IA. O texto da mensagem e a resposta da IA nunca vão para o log.

   A migração `0005` roda no build, como as outras.
8. **Frontend no Render (ADR-0014).** Definir, no serviço do frontend, antes do build:
   - `API_URL_INTERNA=https://verifyscan.onrender.com` — para onde o Next repassa `/api/*` e
     `/health`. É lida no build; sem ela, o build falha;
   - `NEXT_PUBLIC_CONTATO_PRIVACIDADE` — o e-mail que aparece em `/privacidade` para pedir a
     exclusão da conta (o caminho de quem esqueceu a senha; com a senha, a exclusão é feita em
     Minha conta → Meus dados). Sem ela, a página diz "contato em configuração";
   - `NEXT_PUBLIC_URL_DESPERTAR=https://verifyscan.onrender.com` — o endereço público do
     backend. O navegador faz um GET direto a `/health` nele, só para acordá-lo: pelo proxy, o
     Render responde 502 e não acorda o backend (adendo do ADR-0017). Também é lida no build. Sem
     ela, o build passa, mas o primeiro acesso em produção não acorda o backend.

   **`NEXT_PUBLIC_API_URL` pode sair do painel:** o código não a lê mais.

**Não aponte monitor de uptime nem keep-alive para `/health`**: ele faz `SELECT 1` e manteria o
compute do Neon ligado o mês inteiro, estourando a cota gratuita (conta no ADR-0011).

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

**Em produção, o primeiro acesso mostra "O servidor está acordando".**
É o esperado no plano gratuito: o backend do Render dorme depois de 15 min sem uso e leva até
~60 s para acordar. A tela tenta de novo sozinha por até 90 s; envios (análise, entrar, cadastro)
esperam o backend responder e saem uma vez só (ADR-0017). Se passar de 90 s, confira no painel do
Render se o serviço do backend subiu e se `NEXT_PUBLIC_URL_DESPERTAR` está definida no frontend:
sem ela, ninguém acorda o backend. Não crie monitor nem keep-alive para evitar a espera: as
cotas gratuitas não comportam (ADR-0011).

**`uv sync` reclama que o `uv.lock` está desatualizado.**
Alguém mexeu no `pyproject.toml`. Rode `uv lock` e commite o `uv.lock` junto.
