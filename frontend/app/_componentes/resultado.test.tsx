// @vitest-environment jsdom
// A placa do resultado e a reputação dos links (ADR-0028): a atribuição ao Google aparece só no
// que veio do Google, o histórico não a mostra, e a tela avisa quando as bases não responderam.
//
//   npm test

import assert from "node:assert/strict";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, test } from "vitest";

import { AVISO_DO_GOOGLE, Resultado, type DadosDoResultado } from "./resultado";

afterEach(cleanup);

const DO_GOOGLE = "O Google Safe Browsing aponta um link desta mensagem como possivelmente perigoso.";
const DO_VIRUSTOTAL =
  "Um serviço de segurança reunido pelo VirusTotal levanta suspeita sobre um endereço desta mensagem.";

function resultado(mudancas: Partial<DadosDoResultado> = {}): DadosDoResultado {
  return {
    nivel_risco: "ALTO",
    fatores: [
      { categoria: "urgencia", descricao: "A mensagem cria urgência." },
      { categoria: "reputacao_safe_browsing", descricao: DO_GOOGLE },
      { categoria: "reputacao_virustotal_suspeito", descricao: DO_VIRUSTOTAL },
    ],
    links: [
      {
        dominio: "golpe-exemplo.example",
        observacoes: ["apontado pelo Google Safe Browsing como possivelmente perigoso"],
        apontado_por: ["safe_browsing"],
        conselho: "Não abra o link.",
      },
      {
        dominio: "outro-exemplo.example",
        observacoes: ["há suspeita de um serviço de segurança (VirusTotal) sobre este endereço"],
        apontado_por: ["virustotal"],
        conselho: "Não abra o link.",
      },
    ],
    ...mudancas,
  };
}

test("a atribuição ao Google aparece no fator e no link que vieram dele, e só neles", () => {
  render(<Resultado resultado={resultado()} />);

  const atribuicoes = screen.getAllByRole("link", { name: "Aviso fornecido pelo Google" });

  // Uma no fator do Google, uma no link que o Google apontou. Nenhuma no que veio do VirusTotal.
  assert.equal(atribuicoes.length, 2);
  const itens = atribuicoes.map((a) => a.closest("li")?.textContent ?? "");
  assert.ok(itens[0].startsWith(DO_GOOGLE));
  assert.ok(itens[1].startsWith("golpe-exemplo.example"));
  assert.ok(!screen.getByText(DO_VIRUSTOTAL).closest("li")?.textContent?.includes("Google"));
});

test("o link da atribuição vai à página de aviso do Google, em nova aba e sem referência", () => {
  render(<Resultado resultado={resultado()} />);

  const [atribuicao] = screen.getAllByRole("link", { name: "Aviso fornecido pelo Google" });

  assert.equal(atribuicao.getAttribute("href"), AVISO_DO_GOOGLE);
  assert.equal(atribuicao.getAttribute("target"), "_blank");
  assert.equal(atribuicao.getAttribute("rel"), "noopener noreferrer");
  assert.ok(atribuicao.parentElement?.textContent?.includes("A informação pode não ser precisa."));
});

test("a atribuição é o único link da placa: o domínio continua sendo só texto", () => {
  render(<Resultado resultado={resultado()} />);

  const enderecos = screen.getAllByRole("link").map((a) => a.getAttribute("href"));

  assert.deepEqual([...new Set(enderecos)], [AVISO_DO_GOOGLE]);
  assert.equal(screen.getByText("golpe-exemplo.example").tagName, "SPAN");
});

test("no histórico, o fator de reputação vem neutro e sem atribuição", () => {
  const doHistorico = resultado({
    fatores: [
      {
        categoria: "reputacao",
        descricao:
          "Na data desta análise, uma base de reputação externa apontava este domínio como " +
          "possivelmente perigoso.",
      },
    ],
    // O histórico recalcula os links do texto, sem consultar nada: não há `apontado_por`.
    links: [{ dominio: "golpe-exemplo.example", observacoes: ["nada estranho no endereço"] }],
  });

  render(<Resultado resultado={doHistorico} nivel={3} />);

  assert.ok(screen.getByText(/Na data desta análise/));
  assert.equal(screen.queryByRole("link"), null);
  assert.equal(screen.queryByText(/Aviso fornecido pelo Google/), null);
});

test("avisa quando as bases externas não responderam, e só então", () => {
  const aviso = /Não conseguimos consultar agora as bases externas/;

  const { unmount } = render(
    <Resultado resultado={resultado({ verificacao_externa_indisponivel: true })} />,
  );
  assert.ok(screen.getByText(aviso));
  unmount();

  render(<Resultado resultado={resultado({ verificacao_externa_indisponivel: false })} />);
  assert.equal(screen.queryByText(aviso), null);
});
