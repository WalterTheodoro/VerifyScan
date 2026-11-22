// @vitest-environment jsdom
// O campo de senha com mostrar e ocultar: o botão troca o próprio rótulo, sem `aria-pressed`, e
// cada campo tem nome e botão próprios para o leitor de tela.
//
//   npm test

import assert from "node:assert/strict";
import { fireEvent, render, screen } from "@testing-library/react";
import { test, vi } from "vitest";

import { CampoSenha } from "./campo-senha";

function campo(props: Partial<Parameters<typeof CampoSenha>[0]> = {}) {
  const aoMudar = vi.fn();
  render(
    <CampoSenha
      id="senha"
      autoComplete="current-password"
      valor=""
      aoMudar={aoMudar}
      somenteLeitura={false}
      {...props}
    />,
  );
  return { aoMudar, entrada: screen.getByLabelText<HTMLInputElement>(props.rotulo ?? "Senha") };
}

/** O botão que controla o campo, e o que ele diz. Pelo texto, e não pelo nome acessível
 *  calculado: o cálculo da Testing Library apara o espaço do começo do `sr-only` e junta
 *  "Mostrarsenha", coisa que o texto da página não faz. */
function botaoDe(id: string) {
  const botao = document.querySelector<HTMLButtonElement>(`button[aria-controls="${id}"]`);
  assert.ok(botao);
  return botao;
}

test("começa escondida, ligada ao rótulo, sem correção automática", () => {
  const { entrada } = campo();
  assert.equal(entrada.type, "password");
  assert.equal(entrada.name, "senha");
  assert.equal(entrada.getAttribute("autocomplete"), "current-password");
  assert.equal(entrada.getAttribute("autocapitalize"), "none");
  // O jsdom não implementa a propriedade `spellcheck`: confere o atributo.
  assert.equal(entrada.getAttribute("spellcheck"), "false");
});

test("Mostrar revela a senha e vira Ocultar; Ocultar esconde de novo", () => {
  const { entrada } = campo();
  const botao = botaoDe("senha");
  assert.equal(botao.textContent, "Mostrar senha");
  assert.equal(botao.type, "button");
  assert.equal(botao.hasAttribute("aria-pressed"), false);

  fireEvent.click(botao);
  assert.equal(entrada.type, "text");
  assert.equal(botao.textContent, "Ocultar senha");

  fireEvent.click(botao);
  assert.equal(entrada.type, "password");
  assert.equal(botao.textContent, "Mostrar senha");
});

test("o que se digita vai para quem usa o campo", () => {
  const { aoMudar, entrada } = campo();
  fireEvent.change(entrada, { target: { value: "s3nh@" } });
  assert.deepEqual(aoMudar.mock.calls, [["s3nh@"]]);
});

test("a dica aparece antes do campo e é lida junto com ele", () => {
  const { entrada } = campo({ dica: "Pelo menos 8 caracteres." });
  const dica = screen.getByText("Pelo menos 8 caracteres.");
  assert.equal(dica.id, "senha-dica");
  assert.equal(entrada.getAttribute("aria-describedby"), "senha-dica");
});

test("sem dica, nada descrito", () => {
  const { entrada } = campo();
  assert.equal(entrada.hasAttribute("aria-describedby"), false);
});

test("dois campos no mesmo formulário: nomes e botões distintos", () => {
  campo({ id: "atual", rotulo: "Senha atual", nome: "senha_atual" });
  const { entrada } = campo({
    id: "nova",
    rotulo: "Nova senha",
    nome: "nova_senha",
    autoComplete: "new-password",
  });
  assert.equal(entrada.name, "nova_senha");
  assert.equal(botaoDe("atual").textContent, "Mostrar senha atual");
  assert.equal(botaoDe("nova").textContent, "Mostrar nova senha");
});

test("somente leitura enquanto envia", () => {
  const { entrada } = campo({ somenteLeitura: true });
  assert.equal(entrada.readOnly, true);
});
