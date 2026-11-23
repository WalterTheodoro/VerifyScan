// @vitest-environment jsdom
// O aviso de privacidade só fala do aviso de erro quando o Sentry está ligado (ADR-0026): o texto
// tem de dizer a verdade com e sem a variável.
//
//   npm test

import assert from "node:assert/strict";
import { render, screen } from "@testing-library/react";
import { afterEach, test, vi } from "vitest";

// O componente lê a variável quando o módulo carrega, como no build.
async function carregar() {
  vi.resetModules();
  return (await import("./aviso-privacidade")).AvisoPrivacidade;
}

afterEach(() => {
  vi.unstubAllEnvs();
});

test("sem o Sentry, não há seção sobre erros", async () => {
  vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "");
  const AvisoPrivacidade = await carregar();

  render(<AvisoPrivacidade nivel="h2" />);

  assert.equal(screen.queryByRole("heading", { name: "Quando o site dá erro" }), null);
  assert.equal(screen.queryByText(/Sentry/), null);
});

test("com o Sentry, diz o que vai e o que nunca vai", async () => {
  vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "https://chave@o0.ingest.exemplo.invalid/1");
  const AvisoPrivacidade = await carregar();

  render(<AvisoPrivacidade nivel="h2" />);

  assert.ok(screen.getByRole("heading", { level: 2, name: "Quando o site dá erro" }));
  assert.ok(screen.getByText(/nunca leva a mensagem que você colou, o print/));
  assert.ok(screen.getByText(/sem o endereço IP da sua\s+conexão/));
  assert.ok(screen.getByText(/Não gravamos a sua tela nem o que você digita/));
  // E a lista de com quem os dados ficam passa a citar a Sentry.
  assert.ok(screen.getByText(/Os avisos de erro do site vão para a Sentry/));
});

test("o nível dos títulos acompanha a página", async () => {
  vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "");
  const AvisoPrivacidade = await carregar();

  render(<AvisoPrivacidade nivel="h3" />);

  assert.ok(screen.getByRole("heading", { level: 3, name: "Quem cuida dos seus dados" }));
  assert.equal(screen.queryAllByRole("heading", { level: 2 }).length, 0);
});
