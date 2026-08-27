# ADR-0001 — Stack e ferramentas

**Data:** 2026-08-27 · **Status:** aceito · **Fase:** 0

## Contexto

O RFC §5.6 fixa a stack (Next.js, FastAPI, PostgreSQL, Redis, Tesseract, Claude Haiku 4.5), mas
deixa dois pontos em aberto que travam a Fase 0: a linha "API Backend → PostgreSQL — SQL, via ORM
(SQLAlchemy)" não diz o **paradigma** nem o **driver**, e a §5.4.3 fixa **WHOIS** para idade de
domínio, enquanto o plano de execução usa **RDAP**. O ambiente de desenvolvimento é Windows.
A rota de análise é assíncrona por necessidade: o pipeline chama VirusTotal, Safe Browsing e RDAP
em paralelo com `asyncio.gather`.

## Opções consideradas

1. **ORM síncrono** (SQLAlchemy 2.0 sync + psycopg). Mais simples de escrever e de explicar; mas
   uma chamada síncrona ao banco dentro da rota async bloqueia o event loop, e isso só apareceria
   no teste de carga do RNF02 — tarde demais.
2. **ORM assíncrono com regras explícitas.** Um paradigma só no backend inteiro, ao custo de um
   acesso a banco mais verboso.
3. Manter WHOIS (texto livre, parsing frágil, sem contrato) × trocar por RDAP (JSON padronizado,
   endpoint HTTP, timeout trivial).

## Decisão

Stack do `CLAUDE.md` §2, com **SQLAlchemy 2.0 assíncrono** e quatro regras que existem para
eliminar as armadilhas conhecidas do async:

1. **Driver: psycopg3** (`postgresql+psycopg://`). Fala sync e async com a mesma dependência — a
   decisão é reversível sem trocar de biblioteca.
2. **Nenhum relacionamento lazy.** Toda consulta que precisa de relação usa `selectinload` ou
   `joinedload` explícito. É isso que elimina os erros de `MissingGreenlet`.
3. **`async_sessionmaker` com `expire_on_commit=False`.**
4. **Alembic inicializado com o template async** (`alembic init -t async`).

Idade de domínio via **RDAP** (`rdap.registro.br`, `rdap.org`), com WHOIS apenas como fallback.

## Consequências

- O acesso a banco fica um pouco mais verboso do que precisaria, dado o volume baixo de consultas
  do projeto. É o preço aceito por ter um paradigma só.
- A defesa na banca é uma frase: *o pipeline é paralelo, então o acesso a banco também é async;
  paradigma único elimina uma classe inteira de erro.*
- RDAP diverge do texto do RFC (§5.4.3). Não vira errata — é decisão de implementação, registrada
  aqui e citada no achado 7 de `analise-rfc-v1.1.md`.
- Se o RDAP de um TLD não responder, o fator "idade do domínio" simplesmente não é gerado; ausência
  de sinal não é sinal negativo (ver ADR-0003).
