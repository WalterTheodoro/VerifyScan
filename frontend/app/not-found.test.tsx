// @vitest-environment jsdom
// A página de "não encontrada" em português, com o caminho de volta para a home.
//
//   npm test

import assert from "node:assert/strict";
import { render, screen } from "@testing-library/react";
import { test, vi } from "vitest";

// O cabeçalho e o rodapé têm testes próprios; o da sessão chamaria o backend.
vi.mock("./_componentes/cabecalho", () => ({ Cabecalho: () => <header /> }));
vi.mock("./_componentes/rodape", () => ({ Rodape: () => <footer /> }));

import NaoEncontrada, { metadata } from "./not-found";

test("diz em português que a página não existe", () => {
  render(<NaoEncontrada />);

  assert.ok(screen.getByRole("heading", { level: 1, name: "Página não encontrada" }));
  assert.ok(screen.getByText(/Este endereço não existe no VerifyScan/));
  assert.equal(document.body.textContent?.includes("could not be found"), false);
});

test("leva de volta à página inicial", () => {
  render(<NaoEncontrada />);

  const link = screen.getByRole("link", { name: "Ir para a página inicial" });
  assert.equal(link.getAttribute("href"), "/");
});

test("o título da aba também é em português", () => {
  assert.equal(metadata.title, "Página não encontrada — VerifyScan");
});
