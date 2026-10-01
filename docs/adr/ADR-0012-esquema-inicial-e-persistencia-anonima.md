# ADR-0012 — Esquema inicial, persistência da análise anônima e testes contra Postgres

**Data:** 2026-10-01 · **Status:** aceito · **Fase:** 8

## Contexto

A primeira migração do projeto fixa convenções que, depois de haver dado gravado, só mudam por
migração de renomeação. Ao mesmo tempo, o registro no banco passa a ser I/O dentro da rota de
análise, e precisa de regra para quando falha. E o ADR-0007 mostrou que um bug de banco pode
atravessar ruff, mypy, pytest e CI verdes quando nenhum teste fala com um Postgres real.

## Opções consideradas

- Chave inteira sequencial × **UUID**.
- ENUM nativo do Postgres × **VARCHAR + CHECK nomeado**.
- Falha ao registrar derruba a análise (500) × **a análise sai igual e o registro é descartado**.
- Esquema de teste por `create_all` × **pelo Alembic**.

## Decisão

**Convenções (B1)**
- `naming_convention` no `MetaData` da Base (ix, uq, ck, fk, pk, a da documentação do SQLAlchemy) —
  sem ela o Postgres inventa os nomes que uma migração futura teria de citar.
- PK `Uuid`, gerada em Python com `uuid4` — o id vai aparecer em `/api/historico/{id}`, e inteiro
  sequencial é enumerável.
- Enumeração como VARCHAR + CHECK nomeado — ENUM nativo exige migração manual a cada valor novo, e
  a errata (item 8) já mudou um enum uma vez. Os valores do CHECK no modelo saem do mesmo
  `Literal` do Pydantic: um vocabulário só.
- `DateTime(timezone=True)` com `server_default now()` — o relógio é o do banco, com fuso.
- Relacionamentos com `lazy="raise"` — a regra 2 do ADR-0001 (nada de lazy load) passa a ser
  garantida pelo ORM, não pela memória.

**Tabelas (B2)** — nomes da §5.5 do RFC onde existem.
- `analises`: `id`, `score_risco`, `nivel_risco` (CHECK BAIXO|MEDIO|ALTO), `tipo_input` (CHECK, hoje
  só `texto`), `created_at`.
- `indicadores_risco`: `id`, `analise_id` (FK com `ON DELETE CASCADE`, indexada — o Postgres não
  indexa FK sozinho), `tipo` (CHECK texto|dominio|reputacao, errata item 8), `categoria` (sem
  CHECK: cresce nas Fases 3 e 4, quem valida é o Literal), `descricao`, `peso` (CHECK > 0).
- **Fora, de propósito:**
  - texto da mensagem e `usuario_id` — o ADR-0006 manda `texto_input` nullable, mas o nome e a
    regra dessa coluna dependem do ADR de privacidade do usuário autenticado, ainda não aceito.
    Entram por migração própria;
  - `urls_analisadas` — não está na lista do ADR-0006, e o ADR-0009 preserva a query string, que
    pode carregar e-mail ou token da vítima;
  - `Analise.resultado` — a §5.5 lista o campo sem definir o conteúdo. O único uso de "resultado"
    ligado a persistência é a Tela 5 ("data, resumo e resultado"), onde resultado é o nível de
    risco, já coberto por `nivel_risco`. A explicação da LLM, se a Fase 7 voltar, entra por
    migração própria.
- Migração `0001` gerada por autogenerate e revisada à mão: o autogenerate é rascunho.

**Persistência (B3)**
- `RepositorioAnalises` (Protocol) com implementação Postgres e falso em memória — o padrão do
  `VerificadorSaude`. O repositório recebe um `RegistroAnalise` que **não tem campo** para texto
  nem URL: a regra de privacidade fica no tipo, como a invariante 1.
- Análise e indicadores numa **transação só** (invariante 6): nunca análise sem indicador nem
  conjunto parcial.
- `ServicoAnalise.analisar` continua síncrono e puro — é o que o `avaliar_corpus` chama. A
  orquestração analisar → registrar é o `OrquestradorAnalise`, async, em `services/`; a rota chama
  um método só.
- **Falha ao registrar nunca derruba a análise**: `asyncio.timeout(timeout_persistencia_s)`
  (2 s), transação descartada, log WARNING com o tipo da exceção e nada da mensagem, resposta
  idêntica. Mesma filosofia das invariantes 3 e 4: o banco é auditoria, não pré-requisito para
  responder.

**Testes contra Postgres (A4)**
- Testes marcados `integracao` falam com um Postgres de teste (`TEST_DATABASE_URL`: docker
  compose ou serviço do CI), nunca com o Neon. Todo o resto continua sem rede — porque o bug do
  ADR-0007 só existia contra Postgres real.
- Esquema pelo Alembic (`downgrade base` → `upgrade head` por sessão), nunca `create_all`: assim a
  migração é testada nos dois sentidos.
- Cada teste roda numa transação desfeita no fim; uma conexão nova confere que nenhuma tabela
  ficou com linha. O banco precisa terminar em `_teste` e não pode ser do Neon.
- Sem a variável, local pula; **no CI (`CI=true`) a coleta falha** — CI verde com os testes de
  banco pulados seria o mesmo "verde sem testar" do ADR-0007.
- No Windows, o pytest-asyncio 1.4 cria `ProactorEventLoop` (medido); o conftest de integração
  usa o hook `pytest_asyncio_loop_factories` com `asyncio.SelectorEventLoop` — o mesmo
  `loop_factory` do `alembic/env.py`.
- **O autogenerate do Alembic não compara CHECK constraint**, então o `alembic check` do CI não
  percebe um CHECK divergente. Por isso existe `tests/integracao/test_checks.py`: um caso por
  CHECK, insert por SQL cru, esperando `IntegrityError` — prova que é o banco que recusa.

## Consequências — custo de estar errado

- **Convenção de nomes e tipo de chave decididos depois exigiriam migração de renomeação sobre
  dado já gravado** — e, com a migração no build do Render (ADR-0011), renomeação custa dois
  deploys.
- O registro roda **em série**, depois da análise: no pior caso soma até 2 s aos ≈ 15 s do
  ADR-0002, ≈ 17 s, ainda dentro dos 30 s do RNF01. Medido com o Postgres parado no Windows: a
  resposta sai em 2,2 s, porque a conexão recusada não falha na hora e quem encerra é o timeout.
- Uma análise entregue cujo registro falhou **não fica no banco**. É a troca aceita: perder uma
  linha de auditoria é melhor que negar a resposta a quem está diante de um golpe. O WARNING é o
  rastro, e é o que a observabilidade da Fase 9 vai contar.
- Se o timeout cortar durante o `COMMIT`, o servidor pode concluí-lo: a análise fica gravada e a
  aplicação loga que descartou. O que nunca acontece é conjunto parcial — a transação é atômica.
