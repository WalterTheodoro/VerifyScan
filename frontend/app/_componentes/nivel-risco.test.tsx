// @vitest-environment jsdom
// O vocabulário do nível de risco (ADR-0010): a palavra e o ícone carregam o sentido, nunca só a
// cor. Os três níveis precisam ser distinguíveis pelo desenho.
//
//   npm test

import assert from "node:assert/strict";
import { render } from "@testing-library/react";
import { test } from "vitest";

import { IconeDeRisco, PALAVRA_DO_NIVEL, type NivelRisco } from "./nivel-risco";

test("a palavra de cada nível, com acento só na tela", () => {
  assert.deepEqual(PALAVRA_DO_NIVEL, {
    BAIXO: "Risco baixo",
    MEDIO: "Risco médio",
    ALTO: "Risco alto",
  });
});

/** O desenho do ícone, sem o invólucro: os `d` dos paths e as formas, em ordem. */
function desenho(nivel: NivelRisco): string {
  const { container } = render(<IconeDeRisco nivel={nivel} />);
  const svg = container.querySelector("svg");
  assert.ok(svg);
  return Array.from(svg.children, (filho) => filho.outerHTML).join("");
}

test("cada nível tem um ícone diferente: check, alerta e x", () => {
  const baixo = desenho("BAIXO");
  const medio = desenho("MEDIO");
  const alto = desenho("ALTO");
  assert.equal(new Set([baixo, medio, alto]).size, 3);
  // O check do baixo e o triângulo do médio, para o teste não passar com três desenhos errados.
  assert.match(baixo, /m7\.5 12 3 3 6-6/);
  assert.match(medio, /M12 3 2 20h20L12 3Z/);
  assert.match(alto, /m15 9-6 6/);
});

test("o tamanho vira largura e altura; o traço segue a cor do texto", () => {
  const { container } = render(<IconeDeRisco nivel="ALTO" tamanho={20} />);
  const svg = container.querySelector("svg");
  assert.ok(svg);
  assert.equal(svg.getAttribute("width"), "20");
  assert.equal(svg.getAttribute("height"), "20");
  assert.equal(svg.getAttribute("stroke"), "currentColor");
});

test("sem tamanho, 44 px", () => {
  const { container } = render(<IconeDeRisco nivel="BAIXO" />);
  assert.equal(container.querySelector("svg")?.getAttribute("width"), "44");
});
