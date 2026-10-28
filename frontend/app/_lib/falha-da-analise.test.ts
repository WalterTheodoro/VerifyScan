// A frase de cada falha do envio (correção 9.1): "Verifique sua conexão" só quando não houve
// resposta; com resposta, a frase do servidor.
//
//   npm test

import assert from "node:assert/strict";
import { test } from "node:test";

import { fraseDaFalha, SEM_CONEXAO } from "./falha-da-analise.ts";

const GRANDE = "Esta imagem é grande demais. Envie um print da tela, sem ampliar.";

test("sem resposta (fetch rejeitado, backend que não acordou) é falta de conexão", () => {
  assert.equal(fraseDaFalha({ doBackend: false }), SEM_CONEXAO);
});

test("413 e 422 do backend mostram a frase que veio dele", () => {
  assert.equal(fraseDaFalha({ doBackend: true, status: 413, corpo: { detail: GRANDE } }), GRANDE);
  const naoLeu =
    "Não conseguimos ler uma conversa nesta imagem. Envie um print da mensagem, ou copie e cole " +
    "o texto.";
  assert.equal(fraseDaFalha({ doBackend: true, status: 422, corpo: { detail: naoLeu } }), naoLeu);
});

test("413 sem JSON (cortado no caminho) é o tamanho, não a conexão", () => {
  assert.equal(fraseDaFalha({ doBackend: false, status: 413 }), GRANDE);
});

test("qualquer outra resposta sem frase pede para tentar de novo, nunca fala de conexão", () => {
  for (const resposta of [
    { doBackend: false as const, status: 500 },
    { doBackend: false as const, status: 502 },
    { doBackend: true as const, status: 422, corpo: { detail: [{ loc: ["body"] }] } },
    { doBackend: true as const, status: 500, corpo: null },
  ]) {
    const frase = fraseDaFalha(resposta);
    assert.notEqual(frase, SEM_CONEXAO);
    assert.match(frase, /Tente de novo/);
  }
});
