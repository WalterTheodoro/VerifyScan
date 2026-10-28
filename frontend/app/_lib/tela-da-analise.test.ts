// Quando o erro anterior sai da tela (correção 9.1): ao escolher, colar ou soltar outro arquivo,
// ao remover o print e ao começar uma nova análise.
//
//   npm test

import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { proximaTela, TELA_INICIAL, type Acao, type Tela } from "./tela-da-analise.ts";

type T = Tela<string, string>;
type A = Acao<string, string>;

const depois = (tela: T, ...acoes: A[]) => acoes.reduce(proximaTela<string, string>, tela);

const ERRO_DO_ENVIO = "Não conseguimos ler uma conversa nesta imagem.";
const ERRO_DO_PRINT = "Esta imagem é pequena demais para ler.";

const comErroDoEnvio: T = depois(
  TELA_INICIAL,
  { tipo: "preparou", imagem: "print-1" },
  { tipo: "enviou" },
  { tipo: "respondeu", estado: { situacao: "falhou", mensagem: ERRO_DO_ENVIO } },
);
const comErroDoPrint: T = depois(TELA_INICIAL, { tipo: "escolheu" }, {
  tipo: "nao-preparou",
  mensagem: ERRO_DO_PRINT,
});

const semErro = (tela: T) => tela.aviso === null && tela.estado.situacao !== "falhou";

describe("o erro anterior some", () => {
  // Escolher pelo botão, colar e soltar passam todos por "escolheu".
  const acoes: [string, A][] = [
    ["ao escolher, colar ou soltar outro arquivo", { tipo: "escolheu" }],
    ["ao remover o print", { tipo: "removeu" }],
    ["ao começar uma nova análise", { tipo: "enviou" }],
    ["em Analisar outra mensagem", { tipo: "recomecou" }],
  ];
  for (const [quando, acao] of acoes) {
    test(`do envio, ${quando}`, () => {
      assert.equal(comErroDoEnvio.estado.situacao, "falhou");
      assert.ok(semErro(depois(comErroDoEnvio, acao)));
    });
    test(`do print, ${quando}`, () => {
      assert.equal(comErroDoPrint.aviso, ERRO_DO_PRINT);
      assert.ok(semErro(depois(comErroDoPrint, acao)));
    });
  }
});

test("escolher outro arquivo mantém o print anterior até o novo ficar pronto", () => {
  const tela = depois(comErroDoEnvio, { tipo: "escolheu" });
  assert.equal(tela.imagem, "print-1");
  assert.equal(tela.preparando, true);
  const pronta = depois(tela, { tipo: "preparou", imagem: "print-2" });
  assert.equal(pronta.imagem, "print-2");
  assert.equal(pronta.preparando, false);
});

test("o print recusado substitui o erro do envio: um erro por vez", () => {
  const tela = depois(comErroDoEnvio, { tipo: "escolheu" }, {
    tipo: "nao-preparou",
    mensagem: ERRO_DO_PRINT,
  });
  assert.equal(tela.estado.situacao, "pronta");
  assert.equal(tela.aviso, ERRO_DO_PRINT);
  assert.equal(tela.preparando, false);
});

test("remover e recomeçar tiram o print; enviar o mantém", () => {
  assert.equal(depois(comErroDoEnvio, { tipo: "removeu" }).imagem, null);
  assert.equal(depois(comErroDoEnvio, { tipo: "recomecou" }).imagem, null);
  const enviando = depois(comErroDoEnvio, { tipo: "enviou" });
  assert.equal(enviando.imagem, "print-1");
  assert.deepEqual(enviando.estado, { situacao: "analisando", doPrint: true });
});

test("digitar tira o aviso do print, como antes", () => {
  assert.equal(depois(comErroDoPrint, { tipo: "digitou" }).aviso, null);
});
