// @vitest-environment jsdom
// O logo do cabeçalho: com o nome, o leitor de tela lê o texto; só o símbolo, lê o rótulo.
//
//   npm test

import assert from "node:assert/strict";
import { render, screen } from "@testing-library/react";
import { describe, test, vi } from "vitest";

import { Logo } from "./logo";

// A fonte do Google só existe no build do Next; aqui basta uma classe qualquer.
vi.mock("next/font/google", () => ({ Sora: () => ({ className: "fonte-sora" }) }));

/** Espessura dos dois traços do símbolo: moldura e check. */
function tracos(container: HTMLElement) {
  return Array.from(container.querySelectorAll("path"), (p) => p.getAttribute("stroke-width"));
}

describe("com o nome", () => {
  test("o nome é texto de verdade, na fonte da marca; o símbolo fica oculto", () => {
    const { container } = render(<Logo />);
    const nome = screen.getByText("Verify").parentElement;
    assert.ok(nome);
    assert.equal(nome.textContent, "VerifyScan");
    assert.equal(nome.className, "fonte-sora");
    assert.equal(container.querySelector("svg")?.getAttribute("aria-hidden"), "true");
    assert.equal(screen.queryByRole("img"), null);
  });

  test("o nome acompanha o símbolo: 75% da altura", () => {
    render(<Logo size={48} />);
    const nome = screen.getByText("Verify").parentElement;
    assert.equal(nome?.style.fontSize, "36px");
  });

  test("variante escura troca as cores", () => {
    render(<Logo variant="dark" />);
    assert.equal(screen.getByText("Verify").style.color, "rgb(255, 255, 255)");
    assert.equal(screen.getByText("Scan").style.color, "rgb(125, 152, 255)");
  });
});

describe("só o símbolo", () => {
  test("vira imagem com o nome no rótulo, e não há texto", () => {
    render(<Logo markOnly />);
    const imagem = screen.getByRole("img", { name: "VerifyScan" });
    assert.ok(imagem);
    assert.equal(screen.queryByText("Verify"), null);
  });
});

test("em tamanho pequeno o traço engrossa, para o símbolo não sumir", () => {
  const pequeno = render(<Logo size={32} />);
  assert.deepEqual(tracos(pequeno.container), ["6", "7.5"]);
  pequeno.unmount();
  const grande = render(<Logo size={64} />);
  assert.deepEqual(tracos(grande.container), ["5", "6.5"]);
});
