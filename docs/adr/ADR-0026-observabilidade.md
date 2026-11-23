# ADR-0026 — Observabilidade: logs estruturados, métricas e rastreamento de erros

**Data:** 2026-11-23 · **Status:** aceito · **Fase:** fatia 12

## Contexto

O Portfolio Playbook exige os três pilares de observabilidade. O projeto tinha só logs de texto
livre no terminal do Render: sem id para ligar as linhas de uma requisição, sem contagem de nada e
sem aviso quando algo quebrava. Um erro no navegador era invisível.

A restrição que manda na fatia é a de privacidade. O produto recebe mensagens suspeitas, que
trazem dados de quem as recebeu e de terceiros; as invariantes 1 a 3 já proíbem o conteúdo em log.
Observabilidade é, por definição, tirar dados do processo. A regra aqui: **só sai metadado.**

## Opções consideradas

- **Só os logs da plataforma (Render):** não exige nada, mas não conta, não avisa e não vê o
  navegador. Não atende ao requisito.
- **OpenTelemetry completo** (traces, métricas e logs por um coletor): é o padrão aberto, mas pede
  um coletor e um destino para cada sinal, e a instrumentação automática anota por padrão o que
  esta fatia proíbe (URL inteira, consultas, cabeçalhos). Para um serviço só, o custo de operar e
  de auditar não se paga. Fica como caminho se o projeto ganhar um segundo serviço.
- **Logs JSON com a biblioteca padrão + métricas no formato do Prometheus + Sentry para erros.**

## Decisão

Três peças pequenas, cada uma desligável, e uma regra de privacidade testada nas três.

### O que nunca sai do processo

Texto da mensagem, transcrição do print, imagem, URL ou domínio analisado, e-mail, senha, IP ou
HMAC do IP, id do usuário, corpo de requisição, query string, cookies, os cabeçalhos
`Authorization`, `Cookie`, `X-VerifyScan-IP`, `X-VerifyScan-Segredo` e `X-Forwarded-For`, e nenhum
segredo. **O que sai:** tipo, nível, duração, status, motivo de falha, template da rota.

### Logs (`app/core/logs.py`)

- Uma linha JSON por log, com `ts`, `nivel`, `evento`, `request_id`, `logger` e os campos do
  evento. Formatter próprio sobre o `logging` da biblioteca padrão, sem dependência.
  `LOG_FORMAT=texto` dá o formato legível para o terminal local.
- **De uma exceção saem o tipo e a pilha (arquivo:linha:função). A mensagem nunca.** É nela que o
  conteúdo vaza: o erro de validação do Pydantic cita o valor recebido, e o do driver cita a linha.
- **O uvicorn passa pelo mesmo formatter.** Numa exceção não tratada ele logava o traceback
  inteiro, com a mensagem. Esse vazamento já existia antes desta fatia.
- Os eventos de domínio são campos nos logs que já existiam (`extra=evento(...)`), não linhas
  novas: os testes anteriores, que contam registros, seguem valendo sem mudança.

### Id da requisição (`app/core/requisicao.py`, `frontend/proxy.ts`)

- O proxy do Next gera um UUID e o manda em `X-Request-ID`, trocando o que o navegador tiver
  mandado. O backend aceita o cabeçalho só se for um UUID canônico (ele é alcançável direto da
  internet, e o valor vai para toda linha de log); senão gera outro. Devolve o id na resposta.
- Middleware ASGI puro, e não o `BaseHTTPMiddleware`: aquele embrulha o corpo do pedido, e a rota
  do print lê o corpo aos pedaços.
- Um log por requisição: método, **template da rota**, status e duração. Sem rota casada, o nome é
  `nao_mapeada`: o caminho cru é texto de quem pediu. `/health` e `/metrics` ficam fora do log e
  das métricas HTTP.

### Eventos de domínio

| Evento | Campos |
|---|---|
| `analise_concluida` | `tipo` (texto, print), `nivel_motor`, `nivel_final`, `ia_usada`, `ia_subiu_nivel`, `duracao_ms`; no print, `qtd_imagens` (hoje sempre 1) |
| `ia_falhou` | `motivo` (timeout, http, forma, outro), `etapa` (analise, leitura) |
| `cota_excedida` | `com_conta`, `teto_global` |
| `teto_global_atingido` | uma vez por dia |
| `login_falhou` | `motivo` (credenciais, limite) |
| `cadastro_bloqueado` | — |
| `ia_desligada` | uma vez, na subida |
| `requisicao` | `metodo`, `rota`, `status`, `duracao_ms` |

- **`ia_falhou` tem conjunto fechado de motivos**, porque o motivo é rótulo de métrica. IA
  desligada não é falha (não há chamada): vira `ia_desligada`, uma vez por processo, sem contador.
  Print ilegível também não: a IA respondeu certo.
- **O teto global entra em `cota_excedida`**, com `teto_global: true`. Para isso `SituacaoCota`
  ganhou um booleano que nenhuma decisão lê; há teste comparando a sequência de decisões.

### Métricas (`app/core/metricas.py`, `GET /metrics`)

`prometheus-client` 0.26.0 (24/07/2026), num registro próprio.

| Métrica | Tipo | Rótulos |
|---|---|---|
| `verifyscan_analises_total` | contador | `tipo`, `nivel_final` |
| `verifyscan_analise_duracao_segundos` | histograma | `tipo` |
| `verifyscan_ia_falhas_total` | contador | `motivo` |
| `verifyscan_ia_subiu_nivel_total` | contador | — |
| `verifyscan_cota_excedida_total` | contador | `com_conta` |
| `verifyscan_gasto_ia_dolares_hoje` | medidor | — |
| `http_requisicoes_total` | contador | `metodo`, `rota`, `status` |
| `http_duracao_segundos` | histograma | `rota` |

- **Proteção:** `Authorization: Bearer <METRICS_TOKEN>`, comparado com `hmac.compare_digest`. Sem
  `METRICS_TOKEN` a rota responde 404. O token tem mínimo de 32 caracteres.
- **Todo rótulo é de conjunto fechado.** O método HTTP fora da lista conhecida vira `OUTRO`: quem
  pede escolhe o texto dele, e rótulo aberto é vazamento e série nova a cada valor.
- **O medidor do gasto é atualizado a cada análise**, e não lido do banco na coleta. A reserva da
  cota já lê o gasto do dia antes de cada chamada à IA, e o registro do gasto devolve o total: a
  métrica aproveita as duas leituras, sem consulta nova. Ler na coleta acordaria o Neon a cada
  raspagem e poria I/O de banco numa rota de infraestrutura.

### Erros (Sentry)

`sentry-sdk[fastapi]` 2.74.0 e `@sentry/nextjs` 11.11.0 (ambos de 05/11/2026). **Ligados só com
`SENTRY_DSN` (backend) e `NEXT_PUBLIC_SENTRY_DSN` (frontend).** Sem a variável, o SDK nem é
inicializado: é o estado dos testes e do CI.

- **Backend:** `send_default_pii=False`, `max_request_body_size="never"`,
  `include_local_variables=False`, amostragem de 0,1, `release` por `APP_VERSION` ou
  `RENDER_GIT_COMMIT`. `before_send` e `before_send_transaction` são a mesma função, que deixa no
  pedido só o método e os cabeçalhos permitidos, e tira usuário, rastro e a mensagem da exceção.
- **Integrações automáticas desligadas.** Conferido no código da 2.74.0: a integração com o SDK da
  Anthropic liga sozinha e **captura por conta própria as exceções da chamada**, mesmo as que o
  `AnalisadorIA` trata. Toda queda no plano B viraria um erro no Sentry, com a mensagem da API. O
  prompt só iria com `send_default_pii`, mas a integração inteira fica de fora, junto com as do
  SQLAlchemy e do cliente HTTP. Entram só as do FastAPI e do Starlette.
- **Frontend:** sem Session Replay (gravaria o texto digitado; não está nas integrações padrão e
  nenhum arquivo o liga), `sendDefaultPii: false`, amostragem de 0,1, mesma limpeza do backend.
  Página de erro global em português, que não mostra o texto do erro.
- **`traceLifecycle: "static"`.** Na versão 11 o padrão é enviar os trechos de desempenho em
  fluxo, e o `beforeSendTransaction` é **ignorado**. O SDK avisa no terminal; foi assim que
  apareceu. Com `static` a transação sai inteira e passa pela limpeza.
- **Source maps só com `SENTRY_AUTH_TOKEN`.** Sem o token o build passa igual (conferido).

### O túnel do Sentry

O navegador manda os eventos para o nosso domínio (`/monitoramento`), e a rota
`app/sentry-tunnel/route.ts` os reenvia. Bloqueador de anúncio não barra, e o navegador não abre
conexão com um terceiro.

- **O túnel do SDK repassa o IP do visitante**, nos dois modos (conferido no código da 11.11.0):
  na reescrita, o pedido vai com os cabeçalhos; na rota pronta, ela monta um
  `X-Sentry-Forwarded-For` a partir do `x-forwarded-for`.
- **Por isso a rota é nossa:** ela entrega à função do SDK um pedido só com `content-length`,
  `content-type`, `origin` e `user-agent`. Sem os cabeçalhos de IP, o Sentry vê o endereço do
  servidor do Render.
- **Fica fora do `proxy.ts`.** O matcher é fixo (`/api/:path*`, `/health`); há teste travando o
  caminho do túnel fora de `/api`, onde ele ganharia o segredo do proxy e iria para o backend. Não
  passa pela cota.
- Só reenvia eventos do nosso DSN (`allowedDsns`); outro DSN recebe 403 (medido).
- **Mesmo assim**, no projeto do Sentry a opção *Prevent Storing of IP Addresses* deve ficar
  ligada: é a segunda trava, do lado de lá.

### Saúde

**O `/health` não mudou e não foi dividido.** Ele já é a checagem de prontidão: faz `SELECT 1` no
Postgres e `PING` no Redis, sob demanda. Não é um `/health` leve porque o frontend depende de ele
tocar o banco: é o pedido de aquecimento de cada página, que acorda o Neon antes do envio
(ADR-0017), e é o que a tela `/status` mostra. Dividir em `/health` e `/health/pronto` mudaria o
aquecimento, a tela e a rewrite do Next sem ganho para esta fatia. Nenhum ping agendado foi criado.

## Consequências

- **Os contadores vivem na memória do processo.** Zeram a cada reinício — no Render gratuito, a
  cada sono por ociosidade — e, com mais de um worker, cada um conta o seu. Servem para ver taxa e
  proporção numa janela, não totais históricos. O medidor do gasto fica em zero depois de um
  reinício até a primeira análise com IA; a verdade do gasto continua no banco.
- **O painel de métricas fica para depois da decisão de hospedagem.** Hoje `/metrics` existe e
  pode ser consultado à mão; quem raspa e onde se desenha o painel depende de onde o sistema vai
  rodar.
- **Sem a mensagem da exceção, depurar é pelo tipo e pela pilha.** É o preço da regra. O
  `request_id` liga o erro do Sentry às linhas de log da mesma requisição.
- **`login_falhou` com `motivo: limite`** sai também na confirmação de senha de "Meus dados", que
  usa o mesmo limitador.
- **O aviso de privacidade ganhou uma seção** sobre o aviso de erro, que só aparece com
  `NEXT_PUBLIC_SENTRY_DSN`. Diz "fora do Brasil", e não o país: a região do projeto no Sentry
  (Estados Unidos ou União Europeia) é escolhida na criação dele.
- **O `send_default_pii` está marcado como obsoleto** na 2.74.0, a favor de `data_collection`. Foi
  mantido: é a opção pedida, funciona, e o teste de ponta a ponta prova o resultado. Rever ao
  subir de versão.
- **`overrides` do Vite (ADR-0025):** a referência `$vite` passou a quebrar o `npm install` com
  mais um pacote na árvore (`Unable to resolve reference $vite`). Virou a versão literal, `7.3.7`,
  com o mesmo efeito. Nenhum pacote que já existia mudou de versão.
- **Cobertura da prova:** os testes passam um conteúdo marcado pela análise de texto e de print,
  com e sem IA, com a IA falhando de três jeitos, pelo cadastro e pelo login, e procuram a marca
  em todo log, no corpo de `/metrics` e no que o SDK do Sentry enviaria (com o SDK de verdade e o
  transporte em memória). Com a limpeza desligada, esses testes falham.
