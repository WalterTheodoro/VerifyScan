# ADR-0007 — Event loop do asyncio no Windows

**Data:** 2026-08-28 · **Status:** aceito · **Fase:** 0 (fechamento do Gate 0)

## Contexto

O `psycopg` em modo async **se recusa a rodar sobre o `ProactorEventLoop`**, que é o event loop
padrão do `asyncio` no Windows. Como o ambiente de desenvolvimento do projeto é Windows
(`CLAUDE.md` §2) e o acesso ao banco é async de ponta a ponta (ADR-0001), qualquer processo que
nasça com o loop padrão da plataforma perde o Postgres:

```
psycopg.InterfaceError: Psycopg cannot use the 'ProactorEventLoop' to run in async mode.
```

Isso apareceu em dois lugares no Gate 0, com a mesma causa e sintomas diferentes:

1. `alembic upgrade head` saía com código 1 — o `env.py` do template async chama `asyncio.run()`
   cru e herda o loop da plataforma.
2. `uvicorn` **sem** `--reload` subia, mas `/health` respondia `503` com `postgres: erro` e
   `redis: ok`. Com `--reload` funcionava, por acidente: o `asyncio_loop_factory` do uvicorn só
   devolve `ProactorEventLoop` quando a aplicação **não** roda em subprocesso, e `--reload` roda.

O ponto que torna o caso não óbvio: **o uvicorn não consulta a política de event loop do
`asyncio`**. Ele passa um `loop_factory` explícito para o `asyncio.run` (`server.py:77` →
`config.py:538`), e `asyncio.Runner` chama esse factory direto. Definir
`WindowsSelectorEventLoopPolicy` na aplicação, sozinho, **não tem efeito nenhum** sob uvicorn.

## Opções consideradas

1. **Só a política na aplicação.** Medido: não funciona sob uvicorn, pelo motivo acima.
2. **Driver síncrono do psycopg só para o Alembic.** Resolve 1 e não resolve 2, e contraria o
   ADR-0001 (async de ponta a ponta).
3. **Entrypoint próprio** (`python -m app`) que fixa o loop e chama `uvicorn.run(loop="none")`.
   Impossível de esquecer, mas esconde o uvicorn atrás de código nosso e troca o comando que a
   documentação, o `--reload` e qualquer tutorial de FastAPI usam.
4. **Política na aplicação + `--loop none` no comando.** Os dois juntos: a política diz *qual*
   loop; o `--loop none` faz o uvicorn *perguntar* à política em vez de impor o dele.

## Decisão

Opção 4, em três pontos:

- `alembic/env.py` chama `asyncio.run(..., loop_factory=asyncio.SelectorEventLoop)` sob guarda de
  `sys.platform == "win32"`.
- `app/main.py` define `asyncio.WindowsSelectorEventLoopPolicy()` na importação do módulo, sob o
  mesmo guard. É o que serve qualquer processo que importe a aplicação e use `asyncio.run` —
  scripts, teste de carga, `python -m`.
- O comando documentado do uvicorn passa a levar `--loop none`, no `README.md` e no `CLAUDE.md` §3.

Medição que fecha a decisão, com Postgres e Redis reais:

| Execução | `/health` |
|---|---|
| sem `--reload`, sem a política | 503 — `postgres: erro` |
| sem `--reload`, só a política em `main.py` | 503 — `postgres: erro` |
| sem `--reload`, política + `--loop none` | **200 — `status: ok`** |

## Consequências

- O comando de subir a API tem uma flag que precisa de explicação. É o custo de não esconder o
  uvicorn atrás de um entrypoint nosso; o README explica em três linhas e este ADR sustenta.
- `--loop none` é inofensivo no Linux (o loop padrão de lá já é o Selector) e continua correto com
  ou sem `--reload`, então é uma regra única em vez de uma exceção por ambiente. O que ele custa é
  o `uvloop`, que não é dependência do projeto.
- **Se a Fase 9 fizer deploy em contêiner Linux, este problema não existe lá.** Ele é do ambiente
  de desenvolvimento e de qualquer execução local sem `--reload` — teste de carga e demonstração
  para a banca inclusive, que é onde doeria mais.
- O bug atravessou `ruff`, `mypy`, `pytest` e CI verdes. Nenhum teste podia pegá-lo: a Seção 6 do
  `CLAUDE.md` proíbe teste que faça chamada de rede, e o sintoma só existe contra um Postgres real.
  É o argumento concreto de por que o Gate de infraestrutura é um passo manual do plano.
