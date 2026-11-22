// @vitest-environment jsdom
// A marca tipográfica: para o leitor de tela ela é o nome "VerifyScan", inteiro; o desenho é
// escondido. O traço de marca-texto é montado com as três peças exportadas.
//
//   npm test

import assert from "node:assert/strict";
import { render, screen } from "@testing-library/react";
import { describe, test } from "vitest";

import { GRIFO_MIOLO, GRIFO_PONTA_DIREITA, GRIFO_PONTA_ESQUERDA, Grifo, Marca } from "./marca";

describe("Marca", () => {
  test("o leitor de tela lê o nome inteiro, uma palavra só", () => {
    render(<Marca />);
    const nome = screen.getByText("VerifyScan");
    assert.equal(nome.className, "sr-only");
  });

  test("o desenho (as duas metades e o traço) fica fora da árvore de acessibilidade", () => {
    const { container } = render(<Marca />);
    const desenho = container.querySelector('[aria-hidden="true"]');
    assert.ok(desenho);
    assert.equal(desenho.textContent, "VerifyScan");
    assert.ok(desenho.querySelector("svg"));
  });

  test("cada variante troca as cores do nome e do traço", () => {
    const cores = (variante: "cor" | "mono" | "sobre-escuro") => {
      const { container, unmount } = render(<Marca variante={variante} />);
      const [verify, scan] = container.querySelectorAll<HTMLElement>("[style]");
      const traco = container.querySelector("g")?.getAttribute("fill");
      const resultado = [verify.style.color, scan.style.color, traco].join(" | ");
      unmount();
      return resultado;
    };
    assert.equal(cores("cor"), "var(--tinta) | var(--anil) | var(--rosa-marcador)");
    assert.equal(cores("mono"), "var(--tinta) | var(--tinta) | #d4d6dc");
    // O jsdom escreve o #ffffff do código como rgb.
    assert.equal(
      cores("sobre-escuro"),
      "rgb(255, 255, 255) | var(--anil-profundo) | var(--rosa-marcador)",
    );
  });

  test("o tamanho vem de fora, pela classe", () => {
    const { container } = render(<Marca className="text-[40px]" />);
    assert.match(container.firstElementChild?.className ?? "", /text-\[40px\]/);
  });
});

describe("Grifo", () => {
  test("ponta + miolo + ponta, encaixados lado a lado, sem ser lido", () => {
    const { container } = render(<Grifo cor="red" />);
    const svg = container.querySelector("svg");
    assert.ok(svg);
    assert.equal(svg.getAttribute("aria-hidden"), "true");
    assert.equal(svg.getAttribute("viewBox"), "0 0 72 24");
    const pecas = Array.from(svg.querySelectorAll("path"), (p) => [
      p.getAttribute("d"),
      p.getAttribute("transform"),
    ]);
    assert.deepEqual(pecas, [
      [GRIFO_PONTA_ESQUERDA, null],
      [GRIFO_MIOLO, "translate(6 0)"],
      [GRIFO_PONTA_DIREITA, "translate(66 0)"],
    ]);
  });
});
