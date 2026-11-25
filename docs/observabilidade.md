# Observabilidade

Como ver o que o VerifyScan está fazendo: logs, métricas e erros. As decisões e os porquês estão
no [ADR-0026](adr/ADR-0026-observabilidade.md).

**Regra que vale para os três:** só sai metadado (tipo, nível, duração, status, motivo). Nunca o
texto da mensagem, o print, um link analisado, e-mail, senha, IP, id de usuário, cookie ou segredo.

## Logs

Uma linha JSON por log, na saída do processo.

- **Em produção:** painel do Render → serviço do backend → **Logs**.
- **Localmente:** o terminal do `uvicorn`. Com `LOG_FORMAT=texto` no `.env`, saem legíveis.

```json
{"ts": "2026-11-23T02:54:37.905396+00:00", "nivel": "INFO", "evento": "analise_concluida", "request_id": "22d60208-6f7f-4429-9a9a-9a714fea1b17", "logger": "app.services.orquestrador", "tipo": "texto", "nivel_motor": "ALTO", "nivel_final": "ALTO", "ia_usada": false, "ia_subiu_nivel": false, "duracao_ms": 27}
```

| Campo | O que é |
|---|---|
| `ts` | data e hora em UTC |
| `nivel` | `DEBUG`, `INFO`, `WARNING` ou `ERROR` (o mínimo é o `LOG_LEVEL`) |
| `evento` | o nome do evento; `log` para uma linha sem evento, que traz `mensagem` |
| `request_id` | o id da requisição; `null` fora de uma requisição (subida, faxina) |
| `erro`, `pilha` | de uma exceção: o tipo e a lista de `arquivo:linha:função`. Nunca a mensagem dela |

### Seguir uma requisição

Toda resposta do backend traz o cabeçalho `X-Request-ID`. No navegador: ferramentas de
desenvolvedor → Rede → o pedido → cabeçalhos da resposta. Procure esse valor nos logs do Render
para ver todas as linhas daquela requisição.

### Eventos

| Evento | Quando | Campos |
|---|---|---|
| `requisicao` | uma por requisição (menos `/health` e `/metrics`) | `metodo`, `rota` (o template, ex. `/api/historico/{analise_id}`), `status`, `duracao_ms` |
| `analise_concluida` | a análise saiu | `tipo` (`texto`, `print`), `nivel_motor`, `nivel_final`, `ia_usada`, `ia_subiu_nivel`, `duracao_ms`, `qtd_imagens` (só no print) |
| `ia_falhou` | a chamada à IA caiu no plano B | `motivo` (`timeout`, `http`, `forma`, `outro`), `etapa` (`analise`, `leitura`) |
| `cota_excedida` | a IA foi negada pela cota ou pelo teto | `com_conta`, `teto_global` |
| `teto_global_atingido` | o gasto do dia passou do teto (uma vez por dia) | — |
| `login_falhou` | senha errada, ou limite de tentativas | `motivo` (`credenciais`, `limite`) |
| `cadastro_bloqueado` | limite de contas novas por conexão no dia | — |
| `ia_desligada` | na subida, com `IA_ATIVADA=false` | — |

## Métricas

`GET /metrics` no backend, no formato do Prometheus. Precisa do token.

```powershell
curl.exe -H "Authorization: Bearer $env:METRICS_TOKEN" https://SEU-BACKEND.onrender.com/metrics
```

Localmente, com o backend de pé e o `METRICS_TOKEN` do `.env` carregado na variável:

```powershell
curl.exe -H "Authorization: Bearer $env:METRICS_TOKEN" http://localhost:8000/metrics
```

- Sem `METRICS_TOKEN` configurado no backend: **404**.
- Com token errado ou sem o cabeçalho: **401**.

| Métrica | Tipo | Rótulos | O que responde |
|---|---|---|---|
| `verifyscan_analises_total` | contador | `tipo`, `nivel_final` | quantas análises, de que tipo e com que resultado |
| `verifyscan_analise_duracao_segundos` | histograma | `tipo` | quanto tempo a análise leva (KPI: menos de 30 s) |
| `verifyscan_ia_falhas_total` | contador | `motivo` | com que frequência a IA cai no plano B, e por quê |
| `verifyscan_ia_subiu_nivel_total` | contador | — | em quantas análises a IA subiu o nível do motor |
| `verifyscan_cota_excedida_total` | contador | `com_conta` | quantas análises ficaram sem IA pela cota ou pelo teto |
| `verifyscan_gasto_ia_dolares_hoje` | medidor | — | o gasto com a IA no dia de São Paulo |
| `http_requisicoes_total` | contador | `metodo`, `rota`, `status` | volume e erros por rota |
| `http_duracao_segundos` | histograma | `rota` | tempo de resposta por rota |

**Limitações:** os contadores ficam na memória do processo. Zeram quando o backend reinicia (no
Render gratuito, a cada sono por ociosidade), e com mais de um worker cada um conta o seu. O
medidor do gasto só é atualizado quando há análise com IA; o valor certo está sempre no banco
(`gasto_diario_ia`). Ainda não há painel: fica para depois da decisão de hospedagem.

## Erros (Sentry)

Em <https://sentry.io>, no projeto do VerifyScan → **Issues**. Cada erro mostra o tipo, a pilha, a
rota e a versão (`release`). **Não mostra a mensagem da exceção**: ela é removida antes do envio,
porque pode citar o que a pessoa mandou.

Para ir de um erro aos logs: abra o erro → **Request** → cabeçalho `X-Request-ID` → procure esse
valor nos logs do Render.

Desempenho (10% das requisições): **Performance** / **Traces**.

### Ligar

| Onde | Variável | Efeito |
|---|---|---|
| backend (Render) | `SENTRY_DSN` | liga o Sentry no backend |
| backend | `SENTRY_ENVIRONMENT` | nome do ambiente (vazio: `APP_ENV`) |
| backend | `SENTRY_TRACES_SAMPLE_RATE` | fração de requisições medidas (padrão 0.1) |
| backend | `APP_VERSION` | versão em cada erro (vazio: `RENDER_GIT_COMMIT`, que o Render define) |
| frontend (Render) | `NEXT_PUBLIC_SENTRY_DSN` | liga o Sentry no navegador e no servidor do Next, a rota do túnel e a seção do aviso de privacidade. **Lida no build** |
| frontend | `NEXT_PUBLIC_SENTRY_ENVIRONMENT` | nome do ambiente |
| frontend | `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, `SENTRY_PROJECT` | envio dos source maps no build; sem eles o build passa igual e a pilha sai minificada |

Sem as variáveis de DSN, nada é inicializado e nada sai. Ligue as duas juntas: o aviso de
privacidade só fala do Sentry quando o frontend está com a dele.

### No painel do Sentry

- Organização `verifyscan`, **região Estados Unidos**; projetos `verifyscan-backend` e
  `verifyscan-frontend`.
- **Security & Privacy da organização: Require Data Scrubber, Require Using Default Scrubbers e
  Prevent Storing of IP Addresses, ligados.** Valem para todos os projetos. O site já não manda o
  IP do visitante (o evento passa pelo nosso servidor, que o repassa sem o endereço); esta é a
  segunda trava.
- Alerta "E-mail a cada erro novo (backend e frontend)": issue novo, que escala ou que volta.
- O aviso de privacidade diz que os servidores da Sentry ficam nos Estados Unidos. Se a região
  mudar, o aviso muda junto.

### O que cada envio leva (navegador)

Medido em produção em 25/11/2026, lendo o corpo das chamadas ao túnel `/monitoramento` (ADR-0026,
revisão). Os campos abaixo são os nomes; os valores não foram copiados.

| Tipo | Quando | O que leva |
|---|---|---|
| `event` | quando um erro acontece | tipo do erro e pilha (sem a mensagem), página sem query, navegador, versão, ambiente |
| `transaction` | ~1 em cada 10 páginas abertas, sem erro | `request.url` sem query, `User-Agent`, `contexts.react`, `contexts.trace`, medições (`cls`, `fcp`, `fp`, `lcp`, `ttfb`, `connection.rtt`), trechos (`spans`, sem atributos) |
| `session` | **desligado** (era 1 por página aberta) | era `attrs.environment`, `attrs.release`, `attrs.user_agent`, `sid`, `status` e horários |

O idioma, o fuso e o calendário do navegador (`contexts.culture`) também deixaram de ir: a integração que
os anexava foi desligada junto com a das sessões (`INTEGRACOES_DESLIGADAS`, em
`app/_lib/sentry.ts`). Em nenhum dos 15 envelopes medidos havia `ip_address`, `user`,
`request.data`, cookie, URL com query string ou texto digitado no campo da mensagem.

### Servidores (backend e servidor do Next)

Mandam só `event` (erro) e `transaction` (10% das requisições). A contagem de sessões está
desligada nos dois: no backend, `auto_session_tracking=False`; no servidor do Next, sem a
integração `ProcessSession` e com `sessions: false` na integração de HTTP. O runtime edge não
conta sessões.

### O que nunca vai

Corpo do pedido, cookies, query string, os cabeçalhos `Authorization`, `Cookie`,
`X-VerifyScan-IP`, `X-VerifyScan-Segredo` e `X-Forwarded-For`, variáveis locais, a mensagem da
exceção, o rastro de logs e de cliques, a gravação da tela (o Session Replay não é usado), a
contagem de sessões e o idioma e fuso do navegador.

## Saúde

`GET /health` responde o estado do Postgres e do Redis, consultando os dois na hora. A tela
<http://localhost:3000/status> mostra o resultado. Não há ping agendado: o `/health` só roda
quando alguém o chama (a página, ao abrir, para acordar o banco — ADR-0017).
