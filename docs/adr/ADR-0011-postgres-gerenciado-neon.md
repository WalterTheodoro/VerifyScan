# ADR-0011 — Postgres gerenciado (Neon), conexão e migrações

**Data:** 2026-10-01 · **Status:** aceito · **Fase:** 8

## Contexto

O deploy é no plano gratuito do Render. A invariante 6 exige que toda análise registrada grave os
seus indicadores — e em produção nada persistia, porque não havia banco. O banco gratuito precisa
sobreviver até a defesa, que vem depois da entrega (25/10):

- o **Postgres gratuito do Render** expira 30 dias após criado, com 14 de carência — morreria entre
  a entrega e a defesa;
- o **Supabase gratuito** pausa após 7 dias de pouca atividade e só volta retomando manualmente
  no painel — o tipo de falha que aparece na frente da banca.

## Opções consideradas

1. Postgres gratuito do Render.
2. Supabase gratuito.
3. **Neon gratuito.**

## Decisão

- **Neon gratuito**, região **AWS us-west-2** (a mesma do Render em Oregon), **Postgres 16** —
  igual ao `docker compose` e ao CI, para que o que é testado seja o que roda.
- **Conexão direta, sem `-pooler`.** A API é um processo de longa duração com pool próprio, e o
  Neon recomenda conexão direta para migração. Uma só `DATABASE_URL` serve à app e ao Alembic. O
  `pool_pre_ping` que já existe em `core/db.py` cobre a conexão que o Neon derruba ao escalar a
  zero. A string é colada como o Neon a entrega; o `Settings` troca `postgresql://` /
  `postgres://` por `postgresql+psycopg://` (o driver continua o psycopg3, ADR-0001).
- **A migração roda no build command do Render**, porque o *pre-deploy command* é só dos planos
  pagos. Consequência direta: **toda migração é aditiva no mesmo deploy**; remoção e renomeação vão
  em dois deploys (*expand/contract*), porque o build migra o banco antes de a versão nova da API
  substituir a antiga.
- **Nenhuma SDK do Neon no código.** Para a aplicação, é um Postgres com uma URL.

## Consequências — custo de estar errado

- O gratuito tem **0,5 GB e 100 CU-hora/mês** por projeto; estourar **suspende o banco** até o
  ciclo seguinte. Um keep-alive em `/health` (que faz `SELECT 1`) manteria o compute ligado o mês
  inteiro: 0,25 CU × 720 h = **180 CU-h**, quase o dobro da cota.
- O Render dá **750 h/mês para todos os serviços gratuitos da conta**; dois serviços sempre
  acordados dariam 1.440 h.
- **Regra:** nenhum monitor aponta para rota que toca o banco, e não há keep-alive nos serviços. O
  custo aceito é a primeira requisição depois de ociosidade ser lenta (Render acordando + Neon
  saindo do zero) — e o registro dela pode estourar o `timeout_persistencia_s`, o que pela
  ADR-0012 não derruba a análise.
- **Sair do Neon custa** um `pg_dump` pela conexão direta e trocar uma variável.
