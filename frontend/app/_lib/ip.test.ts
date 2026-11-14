// O IP do visitante que o proxy do Next repassa ao backend (fatia 10, ADR-0024).
//
//   npm test

import assert from "node:assert/strict";
import { test } from "node:test";

import { CABECALHO_IP, CABECALHO_SEGREDO, cabecalhosParaOBackend, ipDoVisitante } from "./ip.ts";

const SEGREDO = "segredo-do-proxy-com-mais-de-32-caracteres";

test("vale a entrada mais à direita: a da esquerda pode ter vindo do navegador", () => {
  assert.equal(ipDoVisitante("1.2.3.4, 203.0.113.9"), "203.0.113.9");
  assert.equal(ipDoVisitante(" 203.0.113.9 "), "203.0.113.9");
  assert.equal(ipDoVisitante("1.2.3.4, 2001:db8::1"), "2001:db8::1");
});

test("sem cabeçalho, ou com a última entrada inválida, não há IP", () => {
  for (const encaminhado of [null, "", "1.2.3.4, lixo", "300.1.1.1", "203.0.113.9:443", "1.2.3"]) {
    assert.equal(ipDoVisitante(encaminhado), null, String(encaminhado));
  }
});

test("com o segredo, repassa o IP e o segredo", () => {
  const recebidos = new Headers({ "x-forwarded-for": "1.2.3.4, 203.0.113.9", cookie: "a=b" });

  const enviados = cabecalhosParaOBackend(recebidos, SEGREDO);

  assert.equal(enviados.get(CABECALHO_IP), "203.0.113.9");
  assert.equal(enviados.get(CABECALHO_SEGREDO), SEGREDO);
  assert.equal(enviados.get("cookie"), "a=b");
});

test("o que o navegador mandou nos cabeçalhos do proxy é sempre trocado ou apagado", () => {
  const forjados = new Headers({
    [CABECALHO_IP]: "198.51.100.1",
    [CABECALHO_SEGREDO]: "chute",
    "x-forwarded-for": "203.0.113.9",
  });

  const comSegredo = cabecalhosParaOBackend(forjados, SEGREDO);
  assert.equal(comSegredo.get(CABECALHO_IP), "203.0.113.9");
  assert.equal(comSegredo.get(CABECALHO_SEGREDO), SEGREDO);

  const semSegredo = cabecalhosParaOBackend(forjados, undefined);
  assert.equal(semSegredo.get(CABECALHO_IP), null);
  assert.equal(semSegredo.get(CABECALHO_SEGREDO), null);
});

test("sem IP válido, não manda o segredo sozinho", () => {
  const enviados = cabecalhosParaOBackend(new Headers(), SEGREDO);

  assert.equal(enviados.get(CABECALHO_IP), null);
  assert.equal(enviados.get(CABECALHO_SEGREDO), null);
});

test("não muda os cabeçalhos recebidos", () => {
  const recebidos = new Headers({ [CABECALHO_IP]: "198.51.100.1" });

  cabecalhosParaOBackend(recebidos, SEGREDO);

  assert.equal(recebidos.get(CABECALHO_IP), "198.51.100.1");
});
