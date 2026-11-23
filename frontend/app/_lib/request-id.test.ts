// O id da requisição que o proxy do Next manda ao backend (ADR-0026).
//
//   npm test

import assert from "node:assert/strict";
import { NextRequest } from "next/server";
import { afterEach, test, vi } from "vitest";

import { proxy } from "../../proxy";
import { CABECALHO_IP, CABECALHO_SEGREDO } from "./ip";
import { CABECALHO_REQUEST_ID, comRequestId } from "./request-id";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const SEGREDO = "segredo-do-proxy-com-mais-de-32-caracteres";

/** O Next devolve os cabeçalhos do PEDIDO reescrito dentro da resposta do proxy, com este
 *  prefixo: é assim que o `NextResponse.next({ request })` os entrega ao roteador. */
function enviadoAoBackend(resposta: Response, nome: string): string | null {
  return resposta.headers.get(`x-middleware-request-${nome}`);
}

afterEach(() => {
  vi.unstubAllEnvs();
});

test("gera um UUID", () => {
  const cabecalhos = comRequestId(new Headers());

  assert.match(cabecalhos.get(CABECALHO_REQUEST_ID) ?? "", UUID);
});

test("cada chamada gera um id diferente", () => {
  const um = comRequestId(new Headers()).get(CABECALHO_REQUEST_ID);
  const outro = comRequestId(new Headers()).get(CABECALHO_REQUEST_ID);

  assert.notEqual(um, outro);
});

test("troca o que o navegador mandou", () => {
  const cabecalhos = comRequestId(new Headers({ "x-request-id": "escolhido-pelo-navegador" }));

  assert.match(cabecalhos.get(CABECALHO_REQUEST_ID) ?? "", UUID);
});

test("mantém os outros cabeçalhos", () => {
  const cabecalhos = comRequestId(new Headers({ cookie: "a=b" }), "id-fixo");

  assert.equal(cabecalhos.get("cookie"), "a=b");
  assert.equal(cabecalhos.get(CABECALHO_REQUEST_ID), "id-fixo");
});

test("o proxy manda o X-Request-ID ao backend, junto com o que já mandava", () => {
  vi.stubEnv("PROXY_SEGREDO", SEGREDO);
  const pedido = new NextRequest("https://verifyscan.exemplo/api/analises", {
    method: "POST",
    headers: { "x-forwarded-for": "1.2.3.4, 203.0.113.9", "x-request-id": "do-navegador" },
  });

  const resposta = proxy(pedido);

  assert.match(enviadoAoBackend(resposta, CABECALHO_REQUEST_ID) ?? "", UUID);
  assert.equal(enviadoAoBackend(resposta, CABECALHO_IP), "203.0.113.9");
  assert.equal(enviadoAoBackend(resposta, CABECALHO_SEGREDO), SEGREDO);
  // É cabeçalho do pedido ao backend, nunca da resposta ao navegador.
  assert.equal(resposta.headers.get(CABECALHO_REQUEST_ID), null);
});

test("o proxy manda o id mesmo sem o segredo", () => {
  vi.stubEnv("PROXY_SEGREDO", "");
  const pedido = new NextRequest("https://verifyscan.exemplo/health");

  const resposta = proxy(pedido);

  assert.match(enviadoAoBackend(resposta, CABECALHO_REQUEST_ID) ?? "", UUID);
  assert.equal(enviadoAoBackend(resposta, CABECALHO_SEGREDO), null);
});
