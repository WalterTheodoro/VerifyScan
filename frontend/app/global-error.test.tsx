// @vitest-environment jsdom
// A página de erro global: avisa o Sentry e fala com a pessoa em português, sem o texto do erro.
//
//   npm test

import assert from "node:assert/strict";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, test, vi } from "vitest";

const sentry = vi.hoisted(() => ({ captureException: vi.fn() }));
vi.mock("@sentry/nextjs", () => sentry);

import ErroGlobal from "./global-error";

const MARCA = "SEGREDO-DO-TESTE-123";

beforeEach(() => {
  sentry.captureException.mockClear();
});

test("mostra uma mensagem amigável em português", () => {
  render(<ErroGlobal error={new Error("boom")} reset={() => {}} />);

  assert.ok(screen.getByRole("heading", { name: "Algo deu errado" }));
  assert.ok(screen.getByText(/Não foi nada que você fez/));
  assert.equal(document.documentElement.lang, "pt-BR");
});

test("o texto do erro não aparece na tela", () => {
  render(<ErroGlobal error={new Error(`falhou ao ler ${MARCA}`)} reset={() => {}} />);

  assert.equal(document.documentElement.textContent?.includes(MARCA), false);
  assert.equal(document.documentElement.textContent?.includes("falhou ao ler"), false);
});

test("reporta o erro ao Sentry, uma vez", () => {
  const erro = new Error("boom");

  const { rerender } = render(<ErroGlobal error={erro} reset={() => {}} />);
  rerender(<ErroGlobal error={erro} reset={() => {}} />);

  assert.equal(sentry.captureException.mock.calls.length, 1);
  assert.equal(sentry.captureException.mock.calls[0][0], erro);
});

test("o botão tenta de novo", () => {
  const reset = vi.fn();
  render(<ErroGlobal error={new Error("boom")} reset={reset} />);

  fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));

  assert.equal(reset.mock.calls.length, 1);
});
