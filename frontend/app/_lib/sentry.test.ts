// O que o frontend manda ao Sentry e o que nunca manda (ADR-0026). Sem o SDK e sem rede.
//
//   npm test

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import path from "node:path";
import { test } from "vitest";

import { config } from "../../proxy";
import {
  CABECALHOS_PROIBIDOS,
  COLETA,
  CAMINHO_DO_TUNEL,
  type EventoDoSentry,
  limparEvento,
  opcoesDoSentry,
  pedidoSemIp,
} from "./sentry";

const MARCA = "SEGREDO-DO-TESTE-123";
const IP = "203.0.113.9";

function eventoFalso() {
  return {
    level: "error",
    message: `mensagem ${MARCA}`,
    logentry: { message: `log ${MARCA}` },
    user: { id: MARCA, ip_address: IP, email: "maria@exemplo.com" },
    request: {
      method: "POST",
      url: `https://verifyscan.exemplo/conta/historico?q=${MARCA}#${MARCA}`,
      query_string: `q=${MARCA}`,
      data: { texto: MARCA, imagem_base64: MARCA },
      cookies: { vs_sessao: MARCA },
      env: { REMOTE_ADDR: IP },
      headers: {
        Authorization: `Bearer ${MARCA}`,
        Cookie: `vs_sessao=${MARCA}`,
        "Set-Cookie": `vs_sessao=${MARCA}`,
        "X-Forwarded-For": `${IP}, 198.51.100.7`,
        "x-real-ip": IP,
        Forwarded: `for=${IP}`,
        "X-VerifyScan-IP": IP,
        "X-VerifyScan-Segredo": MARCA,
        "User-Agent": "Mozilla/5.0",
      },
    },
    breadcrumbs: [{ category: "ui.input", message: `digitou ${MARCA}` }],
    exception: {
      values: [
        {
          type: "SyntaxError",
          value: `Unexpected token 'S', "${MARCA}" is not valid JSON`,
          stacktrace: {
            frames: [{ filename: "app/page.tsx", function: "enviar", vars: { texto: MARCA } }],
          },
        },
      ],
    },
  };
}

test("a limpeza remove todos os campos proibidos", () => {
  const limpo = limparEvento(eventoFalso());

  const serializado = JSON.stringify(limpo);
  assert.equal(serializado.includes(MARCA), false, serializado);
  assert.equal(serializado.includes(IP), false, serializado);
  assert.equal(serializado.includes("maria@exemplo.com"), false, serializado);
  for (const campo of ["data", "cookies", "query_string", "env"]) {
    assert.equal(campo in limpo.request, false, campo);
  }
  for (const campo of ["user", "breadcrumbs", "message", "logentry"]) {
    assert.equal(campo in limpo, false, campo);
  }
  const cabecalhos = Object.keys(limpo.request.headers).map((nome) => nome.toLowerCase());
  for (const proibido of CABECALHOS_PROIBIDOS) {
    assert.equal(cabecalhos.includes(proibido), false, proibido);
  }
});

test("a limpeza deixa o que serve para achar o defeito", () => {
  const limpo = limparEvento(eventoFalso());

  assert.equal(limpo.level, "error");
  assert.equal(limpo.request.method, "POST");
  // A página em que o erro aconteceu, sem a query string e sem o que vem depois do #.
  assert.equal(limpo.request.url, "https://verifyscan.exemplo/conta/historico");
  assert.deepEqual(limpo.request.headers, { "User-Agent": "Mozilla/5.0" });
  const [excecao] = limpo.exception.values;
  assert.equal(excecao.type, "SyntaxError");
  assert.equal("value" in excecao, false);
  assert.deepEqual(excecao.stacktrace.frames, [{ filename: "app/page.tsx", function: "enviar" }]);
});

test("da transação ficam a rota, e os trechos sem os atributos", () => {
  const transacao = {
    type: "transaction",
    transaction: "/conta/historico",
    transaction_info: { source: "route" },
    contexts: { trace: { op: "pageload", data: { "client.address": IP, "url.query": MARCA } } },
    spans: [
      {
        op: "http.client",
        description: `GET /api/historico?q=${MARCA}`,
        data: { "http.query": MARCA, "http.request.header.cookie": MARCA },
      },
    ],
  };

  const limpa = limparEvento(transacao);

  const serializada = JSON.stringify(limpa);
  assert.equal(serializada.includes(MARCA), false, serializada);
  assert.equal(serializada.includes(IP), false, serializada);
  assert.equal(limpa.transaction, "/conta/historico");
  assert.deepEqual(limpa.contexts.trace, { op: "pageload" });
  assert.deepEqual(limpa.spans, [{ op: "http.client", description: "GET /api/historico" }]);
});

test("transação sem rota conhecida perde o caminho cru", () => {
  const transacao = { transaction: `/${MARCA}/qualquer`, transaction_info: { source: "url" } };

  assert.equal(limparEvento(transacao).transaction, "nao_mapeada");
});

test("as transações saem inteiras, para a limpeza valer", () => {
  // Com o padrão do SDK 11 ("stream"), o `beforeSendTransaction` é ignorado.
  assert.equal(opcoesDoSentry("https://chave@o0.ingest.exemplo.invalid/1")?.traceLifecycle, "static");
});

test("evento sem pedido e sem exceção passa igual", () => {
  const evento: EventoDoSentry & { level: string } = { level: "info" };

  assert.deepEqual(limparEvento(evento), { level: "info" });
});

test("sem DSN não há opções: o SDK nem é inicializado", () => {
  for (const dsn of [undefined, "", "   "]) {
    assert.equal(opcoesDoSentry(dsn), null, String(dsn));
  }
});

test("com DSN, as opções obrigatórias", () => {
  const opcoes = opcoesDoSentry(" https://chave@o0.ingest.exemplo.invalid/1 ", "producao");

  assert.ok(opcoes);
  assert.equal(opcoes.dsn, "https://chave@o0.ingest.exemplo.invalid/1");
  assert.equal(opcoes.environment, "producao");
  // O `sendDefaultPii` não existe mais no SDK 11: quem desliga a coleta é o `dataCollection`.
  assert.equal("sendDefaultPii" in opcoes, false);
  assert.equal(opcoes.dataCollection, COLETA);
  assert.equal(opcoes.tracesSampleRate, 0.1);
  assert.equal(opcoes.maxBreadcrumbs, 0);
  assert.equal(opcoes.beforeSend, limparEvento);
  assert.equal(opcoes.beforeSendTransaction, limparEvento);
  // Session Replay gravaria o texto digitado: nenhuma opção dele pode aparecer aqui.
  const nomes = Object.keys(opcoes).join(" ").toLowerCase();
  assert.equal(nomes.includes("replay"), false, nomes);
  assert.equal("integrations" in opcoes, false);
});

test("nenhuma categoria de coleta automática fica ligada", () => {
  assert.equal(COLETA.userInfo, false);
  assert.equal(COLETA.cookies, false);
  assert.equal(COLETA.urlQueryParams, false);
  assert.deepEqual(COLETA.httpBodies, []);
  assert.equal(COLETA.httpHeaders.response, false);
  assert.deepEqual(COLETA.graphQL, { document: false, variables: false });
  assert.deepEqual(COLETA.genAI, { inputs: false, outputs: false });
  assert.deepEqual(COLETA.mcp, { inputs: false, outputs: false });
  assert.equal(COLETA.databaseQueryData, false);
  assert.equal(COLETA.queues, false);
  assert.equal(COLETA.stackFrameVariables, false);
  for (const permitido of COLETA.httpHeaders.request.allow) {
    assert.equal(CABECALHOS_PROIBIDOS.includes(permitido), false, permitido);
  }
});

test("toda categoria que o SDK conhece está declarada", () => {
  // Categoria omitida é categoria COLETADA. A função do SDK que preenche os padrões não é
  // exportada, por isso o caminho do arquivo: se ele mudar numa versão nova, este teste falha e
  // obriga a conferir a lista de novo.
  const sdk = createRequire(import.meta.url)(
    path.resolve(
      "node_modules/@sentry/core/build/cjs/utils/data-collection/resolveDataCollectionOptions.js",
    ),
  );

  const padroes = sdk.resolveDataCollectionOptions({});

  assert.deepEqual(Object.keys(COLETA).sort(), Object.keys(padroes).sort());
  // O padrão do SDK é mesmo coletar: sem o `COLETA`, estas categorias sairiam ligadas.
  assert.equal(padroes.userInfo, true);
  assert.equal(padroes.cookies, true);
  // Com o nosso, o SDK resolve tudo desligado.
  const resolvido = sdk.resolveDataCollectionOptions({ dataCollection: COLETA });
  assert.equal(resolvido.userInfo, false);
  assert.equal(resolvido.cookies, false);
  assert.equal(resolvido.urlQueryParams, false);
  assert.deepEqual(resolvido.httpBodies, []);
});

test("o pedido que vai para o túnel não leva o IP nem o cookie", async () => {
  const recebido = new Request(`https://verifyscan.exemplo${CAMINHO_DO_TUNEL}`, {
    method: "POST",
    headers: {
      "content-type": "text/plain;charset=UTF-8",
      "content-length": "8",
      "user-agent": "Mozilla/5.0",
      origin: "https://verifyscan.exemplo",
      "x-forwarded-for": `${IP}, 198.51.100.7`,
      "cf-connecting-ip": IP,
      "x-vercel-forwarded-for": IP,
      "x-real-ip": IP,
      forwarded: `for=${IP}`,
      cookie: `vs_sessao=${MARCA}`,
      referer: `https://verifyscan.exemplo/conta?q=${MARCA}`,
    },
    body: "envelope",
  });

  const enviado = pedidoSemIp(recebido);

  assert.deepEqual(Object.fromEntries(enviado.headers), {
    "content-length": "8",
    "content-type": "text/plain;charset=UTF-8",
    origin: "https://verifyscan.exemplo",
    "user-agent": "Mozilla/5.0",
  });
  assert.equal(enviado.method, "POST");
  // O corpo segue inteiro.
  assert.equal(await enviado.text(), "envelope");
});

test("o túnel fica fora do proxy do backend", () => {
  // Sob /api, o evento passaria pelo `proxy.ts` (ganharia o segredo do proxy) e seria reescrito
  // para o backend. O matcher é fixo; este teste trava o caminho do túnel fora dele.
  assert.equal(CAMINHO_DO_TUNEL.startsWith("/api"), false);
  assert.equal(CAMINHO_DO_TUNEL.toLowerCase().includes("sentry"), false);
  for (const padrao of config.matcher) {
    const prefixo = padrao.split("/:", 1)[0];
    assert.equal(CAMINHO_DO_TUNEL.startsWith(prefixo), false, padrao);
    assert.equal("/sentry-tunnel".startsWith(prefixo), false, padrao);
  }
});
