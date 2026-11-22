// Trocar senha e excluir a conta (ADR-0019): o que sai para o backend e o que a tela mostra de
// cada resposta. Senha errada volta 400 com `detail`, não 401: só o 401 é "deslogado".
//
//   npm test

import assert from "node:assert/strict";
import { beforeEach, describe, test, vi } from "vitest";

import { MENSAGEM_SEM_SERVIDOR } from "./conta";
import { excluirConta, trocarSenha } from "./gestao-conta";
import { enviarUmaVez, type Resposta } from "./servidor";

vi.mock("./servidor", () => ({ enviarUmaVez: vi.fn() }));

function responder(resposta: Resposta) {
  vi.mocked(enviarUmaVez).mockResolvedValue(resposta);
}

beforeEach(() => {
  vi.mocked(enviarUmaVez).mockReset();
});

describe("o que sai", () => {
  test("trocar senha: POST com a atual e a nova", async () => {
    responder({ doBackend: true, status: 204, corpo: null });
    const opcoes = { aoEsperar: () => {} };
    await trocarSenha("antiga", "nova-senha", opcoes);
    const [caminho, init, repassadas] = vi.mocked(enviarUmaVez).mock.calls[0];
    assert.equal(caminho, "/api/conta/senha");
    assert.equal(init.method, "POST");
    assert.deepEqual(JSON.parse(String(init.body)), {
      senha_atual: "antiga",
      nova_senha: "nova-senha",
    });
    assert.equal(repassadas, opcoes);
  });

  test("excluir: POST só com a senha", async () => {
    responder({ doBackend: true, status: 204, corpo: null });
    await excluirConta("minha-senha", {});
    const [caminho, init] = vi.mocked(enviarUmaVez).mock.calls[0];
    assert.equal(caminho, "/api/conta/excluir");
    assert.deepEqual(JSON.parse(String(init.body)), { senha: "minha-senha" });
  });
});

describe("o que a tela mostra", () => {
  test("204: feito", async () => {
    responder({ doBackend: true, status: 204, corpo: null });
    assert.deepEqual(await excluirConta("x", {}), { situacao: "ok", dados: true });
  });

  test("401: deslogado", async () => {
    responder({ doBackend: true, status: 401, corpo: { detail: "Não autenticado." } });
    assert.deepEqual(await trocarSenha("a", "b", {}), { situacao: "deslogado" });
  });

  test("400 com `detail` (senha atual errada): a frase do backend", async () => {
    responder({ doBackend: true, status: 400, corpo: { detail: "A senha atual não confere." } });
    assert.deepEqual(await trocarSenha("a", "b", {}), {
      situacao: "erro",
      mensagem: "A senha atual não confere.",
    });
  });

  test("422 em lista do FastAPI: pede para conferir", async () => {
    responder({ doBackend: true, status: 422, corpo: { detail: [{ msg: "x" }] } });
    assert.deepEqual(await trocarSenha("a", "b", {}), {
      situacao: "erro",
      mensagem: "Confira os dados e tente de novo.",
    });
  });

  test("5xx sem `detail` e sem backend: a mensagem de sempre", async () => {
    responder({ doBackend: true, status: 500, corpo: {} });
    assert.deepEqual(await excluirConta("x", {}), {
      situacao: "erro",
      mensagem: MENSAGEM_SEM_SERVIDOR,
    });
    responder({ doBackend: false });
    assert.deepEqual(await excluirConta("x", {}), {
      situacao: "erro",
      mensagem: MENSAGEM_SEM_SERVIDOR,
    });
  });
});
