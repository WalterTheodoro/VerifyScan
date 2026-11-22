// @vitest-environment jsdom
// O rodapé de todas as páginas: diz de onde vem o trabalho e leva ao aviso de privacidade.
//
//   npm test

import assert from "node:assert/strict";
import { render, screen } from "@testing-library/react";
import { test } from "vitest";

import { Rodape } from "./rodape";

test("é a região de rodapé da página", () => {
  render(<Rodape />);
  assert.ok(screen.getByRole("contentinfo"));
  assert.ok(screen.getByText(/Trabalho de conclusão de curso de Engenharia de Software/));
});

test("leva ao aviso de privacidade", () => {
  render(<Rodape />);
  const link = screen.getByRole("link", { name: "Aviso de privacidade" });
  assert.equal(link.getAttribute("href"), "/privacidade");
});
