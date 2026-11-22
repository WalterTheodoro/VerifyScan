// @vitest-environment jsdom
// O aviso "Sua conta foi excluída." (ADR-0019) vai pelo sessionStorage, nunca pela URL, e aparece
// uma vez só. Sem storage, não aparece — e nada quebra.
//
//   npm test

import assert from "node:assert/strict";
import { afterEach, beforeEach, test, vi } from "vitest";

import { consumirContaExcluida, marcarContaExcluida } from "./conta-excluida";

beforeEach(() => {
  window.sessionStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

test("sem marca, nada a avisar", () => {
  assert.equal(consumirContaExcluida(), false);
});

test("marcado: avisa uma vez, e a segunda leitura já não acha nada", () => {
  marcarContaExcluida();
  assert.equal(consumirContaExcluida(), true);
  assert.equal(consumirContaExcluida(), false);
  assert.equal(window.sessionStorage.length, 0);
});

test("storage que recusa gravar: marcar não lança", () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new DOMException("cota cheia", "QuotaExceededError");
  });
  assert.doesNotThrow(() => marcarContaExcluida());
  assert.equal(consumirContaExcluida(), false);
});

test("storage que recusa ler: sem aviso, sem erro", () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new DOMException("bloqueado", "SecurityError");
  });
  assert.equal(consumirContaExcluida(), false);
});

test("leu mas não conseguiu apagar: o aviso sai mesmo assim", () => {
  marcarContaExcluida();
  vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
    throw new DOMException("bloqueado", "SecurityError");
  });
  assert.equal(consumirContaExcluida(), true);
});
