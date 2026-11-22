// A frase discreta do "quanto resta" da cota de IA, depois de cada análise (fatia 10, ADR-0024).
//
//   npm test

import assert from "node:assert/strict";
import { test } from "vitest";

import { fraseDoRestante } from "./cota.ts";

test("sem o número (IA desligada, cota não conferida ou backend anterior), nada", () => {
  assert.equal(fraseDoRestante(undefined), null);
  assert.equal(fraseDoRestante(null), null);
});

test("plural e singular", () => {
  assert.equal(fraseDoRestante(24), "Restam 24 análises com IA hoje.");
  assert.equal(fraseDoRestante(3), "Restam 3 análises com IA hoje.");
  assert.equal(fraseDoRestante(1), "Resta 1 análise com IA hoje. Um print conta como 3.");
});

test("abaixo de 3, avisa que o print conta 3: ele seria recusado", () => {
  assert.equal(fraseDoRestante(2), "Restam 2 análises com IA hoje. Um print conta como 3.");
});

test("zero, depois de uma análise com IA: foi a última", () => {
  assert.equal(fraseDoRestante(0), "Esta foi a última análise com IA de hoje.");
});
