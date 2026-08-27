# CLAUDE.md — VerifyScan

> Arquivo de contexto permanente do projeto. O Claude Code lê isto em toda sessão.
> Mantenha curto e denso. Detalhe vai em `docs/`, não aqui.

## 1. O que é

VerifyScan é o TCC de Walter Theodoro Butenes Alves (Engenharia de Software — Católica SC).
Plataforma web que recebe uma mensagem suspeita (texto, link, print ou e-mail) e devolve
**nível de risco (BAIXO / MÉDIO / ALTO) + fatores identificados + recomendação**, em português
acessível a usuários com baixo letramento digital.

O coração do produto é um **pipeline heurístico próprio**. A IA **não decide risco** — ela só
transforma o resultado estruturado em texto legível.

Especificação completa: `docs/RFC-VerifyScan-v1.1.pdf`. Plano de execução: `docs/plano-de-execucao.md`.
Decisões: `docs/adr/`.

## 2. Stack (fixa — não trocar sem ADR)

| Camada | Tecnologia |
|---|---|
| Frontend | Next.js (App Router) + TypeScript + Tailwind |
| Backend | Python 3.12 + FastAPI + Pydantic v2 |
| Pacotes Python | `uv` (não usar pip/poetry direto) |
| ORM / migrações | SQLAlchemy 2.0 (async) + Alembic |
| Banco | PostgreSQL 16 |
| Cache | Redis 7 (TTL 24h) |
| OCR | Tesseract + `pytesseract` (idioma `por`) |
| LLM | Anthropic API — `claude-haiku-4-5` |
| Testes | pytest + pytest-asyncio + httpx.AsyncClient |
| Lint/format | ruff (lint + format) + mypy no backend |
| Infra local | Docker Compose (Postgres + Redis) |

Ambiente de desenvolvimento: **Windows**. Não gerar `Makefile`. Comandos devem funcionar em
PowerShell. Nada de `&&` encadeado em scripts do `package.json` sem alternativa cross-platform.

## 3. Comandos

```powershell
# subir dependências de infra
docker compose up -d

# backend
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

# qualidade (rodar sempre antes de commitar)
uv run ruff format .
uv run ruff check . --fix
uv run mypy app
uv run pytest -q

# avaliação do motor de risco contra o corpus rotulado
uv run python -m tools.avaliar_corpus

# frontend
cd frontend
npm install
npm run dev        # http://localhost:3000
npm run lint
```

## 4. Estrutura

```
verifyscan/
├─ CLAUDE.md
├─ docker-compose.yml
├─ docs/
│  ├─ RFC-VerifyScan-v1.1.pdf
│  ├─ plano-de-execucao.md
│  ├─ diario.md            # log de sessões — vira capítulo da monografia
│  └─ adr/                 # ADR-000N-titulo.md
├─ corpus/
│  ├─ casos/               # YAML rotulado, anonimizado
│  └─ README.md            # proveniência e critério de rotulagem
├─ backend/
│  └─ app/
│     ├─ api/              # rotas FastAPI (finas, sem regra de negócio)
│     ├─ analyzers/        # TextAnalyzer, URLExtractor, DomainAnalyzer, EmailAnalyzer
│     ├─ ocr/              # OCRProcessor
│     ├─ reputation/       # URLChecker + provedores (VirusTotal, SafeBrowsing, Fake)
│     ├─ scoring/          # ScoringEngine + regras.yaml
│     ├─ formulator/       # AIFormulator (LLM)
│     ├─ models/           # SQLAlchemy: Usuario, Analise, IndicadorRisco
│     ├─ schemas/          # Pydantic (contrato da API)
│     └─ core/             # config, segurança, cache, timeouts
│  ├─ tools/               # scripts (avaliar_corpus, etc.)
│  └─ tests/
└─ frontend/
```

## 5. Invariantes — nunca violar

Estas regras vêm do RFC e são o que sustenta a defesa do trabalho. Se uma tarefa parecer exigir
quebrar uma delas, **pare e pergunte**.

1. **A LLM nunca vê conteúdo bruto do usuário** (RF13). O `AIFormulator` recebe apenas um objeto
   tipado com `score`, `nivel_risco` e `fatores[]`. Garanta isso no *tipo*: a função não deve
   aceitar nenhum parâmetro que contenha texto original, imagem ou e-mail. Existe teste para isso.
2. **Nenhuma imagem é persistida além do ciclo de vida da requisição** (RNF06): nunca em banco,
   nunca em diretório da aplicação, nunca em log. O teste verifica que (a) nada foi escrito na
   árvore do projeto e (b) o arquivo temporário não sobrevive ao request — redação que mantém
   `pytesseract` viável (ADR-0006).
3. **O sistema funciona sem a LLM** (RNF08). Se a API cair ou estourar 5s, retorna score + fatores
   com um flag `explicacao_indisponivel: true`. A análise nunca falha por causa da IA.
4. **O sistema funciona sem as APIs externas.** VirusTotal e Safe Browsing são *enriquecimento*.
   Timeout curto, falha silenciosa, flag `verificacao_externa_indisponivel: true`.
5. **Pesos e padrões vivem em `scoring/regras.yaml`**, versionado — nunca espalhados como números
   mágicos no código. Mudar peso não pode exigir mudar código.
6. **Todo ponto somado gera um `IndicadorRisco`** persistido (tipo, descrição, peso). Sem isso não
   há auditoria nem recalibração.
7. **Nada de segredo no repositório.** Chaves só via `.env` (com `.env.example` versionado).
8. **Orçamento de tempo** (KPI < 30s): OCR ≤ 5s **em série** (o texto extraído é a entrada das
   heurísticas) · depois, em paralelo: heurísticas locais ≤ 300ms · RDAP ≤ 3s · reputação externa
   ≤ 5s · por fim LLM ≤ 5s. Pior caso ≈ 15s. Todo I/O externo tem timeout explícito (ADR-0002).

## 6. Convenções de código

- Português nos nomes de domínio (`nivel_risco`, `IndicadorRisco`, `fatores`), inglês em
  termos técnicos consagrados (`cache`, `token`, `handler`). Não misturar dentro do mesmo conceito.
- Type hints obrigatórios no backend; `mypy` limpo.
- Rotas FastAPI são finas: validam entrada, chamam um *service*, devolvem schema. Zero regra de
  negócio em `api/`.
- Analisadores são funções/classes puras: entram dados, saem `list[Fator]`. Sem I/O direto, sem
  acesso a banco. Isso é o que os torna testáveis e é o que será medido contra o corpus.
- Todo acesso a rede fica atrás de uma interface com uma implementação *fake* determinística
  usada nos testes. Teste não faz chamada de rede — nunca.
- Commits em português, imperativo, escopo curto: `feat(scoring): agrega pesos por categoria`.
  Um commit por unidade lógica. Nada de commit gigante de fim de sessão.
- Mensagens ao usuário final em pt-BR, tom direto e não alarmista, sem jargão técnico.

## 7. Como trabalhar comigo (regras para o agente)

- **Planeje antes de escrever.** Em qualquer tarefa que toque mais de 2 arquivos, apresente o
  plano e espere aprovação.
- **Uma tarefa por vez.** Não adiantar fases do plano. Não "aproveitar para arrumar" coisas fora
  do escopo pedido — anote em `docs/diario.md` e siga.
- **Em rodada de correção, corrija UM item por vez**, na ordem em que foi listado. Confirme antes
  de passar ao próximo.
- **Teste antes do código** sempre que houver comportamento verificável. Escreva o teste que
  falha, depois implemente.
- **Não instale dependência nova sem perguntar.** Justifique por que a biblioteca padrão ou o que
  já existe não resolve.
- **Não gere código que eu não consiga explicar numa banca.** Prefira o óbvio ao esperto. Se uma
  solução exigir um truque, comente o porquê em uma linha.
- Ao terminar uma tarefa: rode `ruff`, `mypy`, `pytest`, mostre o resultado e o diff resumido.
- Se algo no RFC estiver ambíguo ou errado, diga — não invente e não finja que está resolvido.

## 8. Definition of Done (por tarefa)

- [ ] Testes novos passam e a suíte inteira continua verde
- [ ] `ruff check` e `mypy` limpos
- [ ] Nenhuma invariante da Seção 5 violada
- [ ] Se mudou comportamento do motor de risco: `avaliar_corpus` rodado, métricas anotadas em
      `docs/diario.md` (antes → depois)
- [ ] Se foi uma decisão de arquitetura: ADR criado em `docs/adr/`
- [ ] Uma linha em `docs/diario.md` com o que foi feito e o que ficou pendente
- [ ] Commit feito

## 9. Contexto acadêmico

Isto é um TCC. A banca vai perguntar **por quê**, não só **o quê**. Portanto:

- Toda escolha não óbvia vira um ADR de 15 linhas (contexto, opções, decisão, consequência).
- O `docs/diario.md` é matéria-prima do capítulo de metodologia — mantenha-o honesto, incluindo
  o que deu errado.
- Números de precisão só valem se vierem do script de avaliação sobre o corpus. Nunca afirme
  precisão sem medição.

