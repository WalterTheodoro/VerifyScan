# ADR-0017 — Espera pelo backend: leituras repetem, envios esperam e saem uma vez

**Data:** 2026-10-26 · **Status:** aceito · **Fase:** 8 (correção)

## Contexto

No Render gratuito, o **serviço** do backend dorme depois de 15 min sem requisição e leva até
~60 s para acordar. O Neon acorda em centenas de milissegundos, então o problema não é o banco. O
frontend repassa `/api/*` e `/health` pelo proxy do Next (ADR-0014, `proxyTimeout` de 90 s).

No primeiro acesso depois de o backend dormir, o `fetch` recebe uma página HTML de erro, e não o
JSON do backend. O sintoma é reproduzível:
- o `/status` mostrava "API inalcançável — Unexpected token '<'";
- quem estava logado via "Entrar", porque a área de sessão tratava falha como "deslogado";
- análise, login e cadastro falhavam na primeira tentativa.

Abrir `/health` do backend direto antes resolvia tudo, o que confirma a causa. A origem exata do
HTML no proxy de produção não foi isolada, e a solução não depende dela. Localmente, com o backend
parado, o proxy responde `500` com `Internal Server Error` em texto: é o mesmo caso.

## Opções consideradas

- **Despertador externo** (cron ou monitor em `/health`): proibido pelo ADR-0011.
- **Repetir tudo automaticamente**, inclusive os envios.
- **Leituras repetem, envios esperam o backend e saem uma vez.**

## Decisão

**1. Uma só classificação**, em `frontend/app/_lib/servidor.ts`:
- **é do backend** toda resposta com corpo JSON, de qualquer status (401, 404, 409, 503 com
  `detail`), e também o **204**, que não tem corpo e só o backend devolve (sair, apagar). A regra
  do "Sair" (ADR-0014) depende dele;
- **é de outra coisa** (proxy, Render): falha de rede, ou resposta sem corpo JSON.

**2. Aquecimento.** Ao abrir a página, um GET silencioso a `/health`, uma vez por carregamento,
sem bloquear nem mostrar nada (`_componentes/aquecimento.tsx`, no layout raiz). O backend começa a
acordar enquanto a pessoa lê.

**3. Leituras repetem sozinhas** (`/api/auth/eu`, `/api/historico`, `/api/conta`, `/health`).
- Se a resposta não veio do backend, tenta de novo com intervalos de 2, 3 e 5 s, depois a cada
  5 s. Nenhuma tentativa nova começa depois de 90 s.
- Durante as tentativas, as telas mostram "O servidor está acordando. Isso pode levar até 1
  minuto." (componente `AvisoAcordando`, um lugar só para o texto).
- No cabeçalho, a área de sessão fica em "carregando", o espaço reservado. **Só o 401 vira
  "deslogado".** Esgotadas as tentativas, mostra "Entrar".
- Em `/api/auth/eu`, o **503 com `detail`** (banco acordando, ADR-0013 §6) também repete.

**4. Envios nunca repetem** (análise, entrar, cadastro, sair, apagar análise ou histórico). O
backend pode ter processado o pedido sem a resposta chegar: repetir o cadastro daria 409 a quem
acabou de se cadastrar, e repetir a análise a gravaria duas vezes.
- Antes de enviar, se o backend não respondeu nos **últimos 10 min**, o envio espera por ele:
  consulta `/health` com a repetição do item 3, mostrando o aviso. Então envia **uma** vez.
- Se o `/health` não respondeu em 90 s, **o envio não sai**, e a tela mostra o erro de hoje.
- Se o próprio envio falhar sem resposta do backend, a tela mostra o erro de hoje, sem repetir.

**5. A janela de 10 min** (`JANELA_ACORDADO_MS`). O Render volta a dormir 15 min depois da última
requisição, **mesmo com a aba aberta**. Uma flag "o backend já respondeu neste carregamento"
deixaria quem abre o site, sai 20 min e volta mandar o envio direto para o backend dormindo, e
receber o mesmo erro de antes. Por isso vale o instante da última resposta do backend, de
qualquer pedido. 10 min fica abaixo dos 15 do Render, com margem para o relógio do Render não
começar a contar no mesmo instante que o nosso.

**6. `/status`.** Sem resposta do backend, frases legíveis ("O servidor está acordando…" durante
as tentativas; "Não conseguimos falar com o servidor." no fim), nunca o erro técnico do JSON. A
dica de comando é a do Windows, com `--loop none` (ADR-0007).

## Por que respeita o ADR-0011

O ADR-0011 proíbe keep-alive: as 750 h/mês do Render para todos os serviços gratuitos e os 100
CU-h/mês do Neon. Esta solução **só acorda o backend quando alguém usa o site**:
- o aquecimento é uma requisição por carregamento de página, disparada pelo navegador de quem
  abriu o site;
- a repetição só existe enquanto a página está aberta e dura no máximo 90 s;
- não há agendador, monitor nem requisição sem uma pessoa do outro lado.

## Consequências — custo de estar errado

- **Um `/health` a mais antes de um envio feito depois de 10 min parado**, mesmo quando o backend
  ainda está acordado (entre 10 e 15 min). Com o backend acordado, custa centenas de milissegundos.
  O `/health` faz `SELECT 1`, mas pela regra acima só existe quando alguém usa o site.
- **Até 90 s de espera no pior caso**, contra o erro imediato de antes. O aviso aparece logo na
  primeira repetição, e a tela não trava.
- **Se o backend processar um envio e a resposta se perder**, a pessoa vê o erro e pode tentar de
  novo à mão. No cadastro, essa segunda tentativa dá 409. É o mesmo custo do ADR-0013 §4,
  agora só no caso raro em que a resposta se perde com o backend já acordado.
- **A lógica nova tem testes** (`frontend/app/_lib/servidor.test.ts`, `node:test`, sem
  dependência nova), que rodam no CI. São os primeiros testes do frontend. Por isso
  `servidor.ts` não importa nada: o Node roda o `.ts` direto e não lê o tsconfig.

## Adendo — 26/10: despertar direto

**Medição em produção, depois do PR #8.** Os dois serviços ficaram 20 min sem requisição.
- Todas as chamadas pelo proxy do Next (`/health` e `/api/auth/eu`) receberam **HTTP 502 por
  3 min seguidos**, das 19:13:24 às 19:16:22, e o backend não acordou.
- Depois disso, **um** GET direto em `https://verifyscan.onrender.com/health` acordou o backend em
  **31,9 s**. Em seguida, o `/health` pelo proxy respondeu 200 em **0,4 s**.
- No log do backend no Render, o processo subiu uma vez só, e o primeiro pedido recebido foi esse
  GET direto, vindo de fora do Render. Nenhum pedido do proxy chegou antes.

**Hipótese (comportamento observado, sem documentação oficial).** O Render responde 502 na hora
aos pedidos que vêm de outro serviço do Render, em vez de acordar o destino. Já o pedido do
navegador ao endereço público acorda. Outro projeto com a mesma arquitetura descreveu o mesmo
comportamento (github.com/BUMETCS673/CS673OLF26P2/pull/86). O teste local do PR #8 não tinha como
pegar isso, porque localmente o proxy alcança o backend sem passar pelo Render.

**Decisão.** A lógica acima continua. O que muda é quem **acorda** o backend.
1. **Variável de build `NEXT_PUBLIC_URL_DESPERTAR`** (em produção,
   `https://verifyscan.onrender.com`).
   - Sem ela, o despertar não acontece e tudo segue como antes.
   - O build não falha por falta dela: localmente o proxy acorda o backend.
2. **`despertar()`** (em `servidor.ts`) faz um `fetch` a `${NEXT_PUBLIC_URL_DESPERTAR}/health` com
   `mode: "no-cors"`, `credentials: "omit"` e `cache: "no-store"`.
   - Não lê a resposta e ignora qualquer erro.
   - Nunca lança e nunca é aguardado.
3. **Onde é chamado:**
   - no `aquecer()`, junto do `/health` pelo proxy;
   - no início do `esperarPeloBackend()`, quando a última resposta do backend é mais velha que
     `JANELA_ACORDADO_MS` ou não existe;
   - em **toda** repetição de uma leitura que não veio do backend (`lerComRepeticao`).

   Nunca sai mais de um a cada 10 s (`INTERVALO_DESPERTAR_MS`), o que dá no máximo ~9 em 90 s.
4. **Por que repetir, e não despertar uma vez só por espera.** Se esse único pedido se perder (rede
   instável no celular), ninguém acorda o backend nos 90 s seguintes. A espera termina em erro, que
   é justamente a falha medida. O intervalo de 10 s é o que impede a rajada.
5. **A confirmação de que o backend está de pé continua sendo uma resposta JSON pelo proxy.** O
   despertar não conta como resposta, até porque, em `no-cors`, a resposta é opaca.

**ADR-0014.** Esta é a **única exceção** a "todo `fetch` do navegador é relativo". O motivo do
ADR-0014 não se aplica: o cookie de terceiro bloqueado pelo Safari só importa quando o pedido leva
cookie, e este vai com `credentials: "omit"` e sem leitura da resposta. Login, análise, histórico
e todo o resto continuam pelo proxy. O comentário de `next.config.ts` registra a exceção.

**ADR-0011.** Continua respeitado: o despertar só sai do navegador de quem está usando o site,
nos mesmos momentos em que a espera já pedia `/health`. Não há agendador nem keep-alive.

**Custo de estar errado.**
- Se o Render passar a acordar pelo proxy, o despertar vira um GET redundante, de no máximo um a
  cada 10 s, e só enquanto alguém espera.
- Se o Render deixar de acordar também pelo navegador, nada desta solução funciona. O caminho
  passa a ser um plano pago (o serviço não dorme) ou um domínio próprio (ADR-0014).
