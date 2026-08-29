# VerifyScan

Plataforma web que recebe uma mensagem suspeita — texto, link, print ou e-mail — e devolve
**nível de risco (BAIXO / MÉDIO / ALTO), os fatores identificados e uma recomendação**, em
português acessível a quem tem pouco letramento digital.

O coração do produto é um pipeline heurístico próprio. A IA **não decide risco**: ela só
transforma o resultado estruturado em texto legível.

TCC de Engenharia de Software — Católica SC. Especificação em `docs/RFC-VerifyScan-v1.1.pdf`,
plano de execução em `docs/plano-de-execucao.md`, decisões em `docs/adr/`.

> **Estado atual: Fase 1 (fatia vertical de texto).** Você cola uma mensagem na tela e recebe
> nível de risco, fatores identificados e o que fazer. Ainda sem OCR, sem consulta a APIs
> externas, sem explicação por IA e sem login — tudo isso vem nas Fases 4 a 8.

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

O `alembic upgrade head` termina sem fazer nada nesta fase (não há tabelas até a Fase 8); rodá-lo
serve para provar que a conexão com o banco funciona.

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
lugar do `ruff format`.

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
│  │  ├─ scoring/      ScoringEngine e regras.yaml (Fase 1)
│  │  ├─ formulator/   AIFormulator (Fase 7)
│  │  ├─ models/       SQLAlchemy (Fase 8)
│  │  ├─ schemas/      Pydantic — o contrato da API
│  │  └─ core/         config, banco, cache, timeouts
│  ├─ alembic/         migrações (nenhuma ainda)
│  ├─ tools/           scripts, incluindo avaliar_corpus (Fase 2)
│  └─ tests/
├─ frontend/           Next.js App Router + TypeScript + Tailwind
├─ corpus/             base rotulada para medir o motor de risco (Fase 2)
├─ docs/               RFC, plano de execução, ADRs e diário de bordo
└─ docker-compose.yml  Postgres 16 e Redis 7
```

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

**A página do frontend mostra "API inalcançável".**
O backend não está no ar, ou está em outra porta. Confira o `uvicorn` e o valor de
`NEXT_PUBLIC_API_URL` em `frontend/.env.local`. Mudança nessa variável exige reiniciar o
`npm run dev` — o Next lê o `.env.local` só na inicialização.

**`uv sync` reclama que o `uv.lock` está desatualizado.**
Alguém mexeu no `pyproject.toml`. Rode `uv lock` e commite o `uv.lock` junto.
