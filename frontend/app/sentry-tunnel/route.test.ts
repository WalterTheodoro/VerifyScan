// A rota do túnel: só existe com DSN, e entrega ao SDK o pedido sem o IP de quem pediu.
//
//   npm test

import assert from "node:assert/strict";
import { afterEach, beforeEach, test, vi } from "vitest";

const DSN = "https://chave@o0.ingest.exemplo.invalid/1";
const IP = "203.0.113.9";

// O SDK de verdade abriria uma conexão com o Sentry. Este falso só anota o que recebeu.
const sdk = vi.hoisted(() => ({
  opcoes: [] as { allowedDsns?: string[] }[],
  pedidos: [] as Request[],
}));
vi.mock("@sentry/nextjs/tunnel", () => ({
  createSentryTunnelRoute: (opcoes: { allowedDsns?: string[] }) => {
    sdk.opcoes.push(opcoes);
    return {
      POST: async (pedido: Request) => {
        sdk.pedidos.push(pedido);
        return new Response(null, { status: 200 });
      },
    };
  },
}));

function pedido(): Request {
  return new Request("https://verifyscan.exemplo/sentry-tunnel", {
    method: "POST",
    headers: {
      "content-length": "8",
      "x-forwarded-for": `${IP}, 198.51.100.7`,
      cookie: "vs_sessao=abc",
    },
    body: "envelope",
  });
}

/** A rota lê o DSN quando o módulo carrega: cada teste o carrega de novo, com o ambiente dele. */
async function carregarRota() {
  vi.resetModules();
  return import("./route");
}

beforeEach(() => {
  sdk.opcoes.length = 0;
  sdk.pedidos.length = 0;
});

afterEach(() => {
  vi.unstubAllEnvs();
});

test("sem DSN a rota responde 404 e não chama o SDK", async () => {
  vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "");
  const { POST } = await carregarRota();

  const resposta = await POST(pedido());

  assert.equal(resposta.status, 404);
  assert.deepEqual(sdk.opcoes, []);
  assert.deepEqual(sdk.pedidos, []);
});

test("com DSN, só reenvia para o nosso projeto", async () => {
  vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", ` ${DSN} `);
  await carregarRota();

  assert.deepEqual(sdk.opcoes, [{ allowedDsns: [DSN] }]);
});

test("o SDK recebe o pedido sem o IP e sem o cookie", async () => {
  vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", DSN);
  const { POST } = await carregarRota();

  const resposta = await POST(pedido());

  assert.equal(resposta.status, 200);
  const [entregue] = sdk.pedidos;
  // O `content-type` é o que o próprio `Request` do teste põe num corpo de texto.
  assert.deepEqual(Object.fromEntries(entregue.headers), {
    "content-length": "8",
    "content-type": "text/plain;charset=UTF-8",
  });
  assert.equal(entregue.headers.has("x-forwarded-for"), false);
  assert.equal(entregue.headers.has("cookie"), false);
  assert.equal(await entregue.text(), "envelope");
});
