// Tradução das respostas de conta (ADR-0013, ADR-0014): o que a tela mostra para cada resposta do
// backend. A espera e a classificação de quem respondeu (`servidor.ts`) têm teste próprio; aqui
// elas são falsas, e cada teste diz o que "chegou".
//
//   npm test

import assert from "node:assert/strict";
import { beforeEach, describe, test, vi } from "vitest";

import { consultarSessao, enviarConta, lerDetail, MENSAGEM_SEM_SERVIDOR, sairDaConta } from "./conta";
import { enviarUmaVez, lerSessao, type Resposta } from "./servidor";

vi.mock("./servidor", () => ({ enviarUmaVez: vi.fn(), lerSessao: vi.fn() }));

const CONFIRA = "Confira os dados e tente de novo.";
const ANA = { nome: "Ana", email: "ana@exemplo.com" };

function responder(resposta: Resposta) {
  vi.mocked(enviarUmaVez).mockResolvedValue(resposta);
}

beforeEach(() => {
  vi.mocked(enviarUmaVez).mockReset();
  vi.mocked(lerSessao).mockReset();
});

test("lerDetail: só o `detail` de um objeto", () => {
  assert.equal(lerDetail({ detail: "Senha incorreta." }), "Senha incorreta.");
  assert.equal(lerDetail({ outra: 1 }), undefined);
  assert.equal(lerDetail(null), undefined);
  assert.equal(lerDetail("texto"), undefined);
});

describe("enviarConta: cadastro e login", () => {
  test("manda o corpo em JSON, por POST, uma vez só", async () => {
    responder({ doBackend: true, status: 200, corpo: ANA });
    await enviarConta("/api/auth/login", { email: "ana@exemplo.com", senha: "x" });
    const [caminho, init] = vi.mocked(enviarUmaVez).mock.calls[0];
    assert.equal(caminho, "/api/auth/login");
    assert.equal(init.method, "POST");
    assert.deepEqual(JSON.parse(String(init.body)), { email: "ana@exemplo.com", senha: "x" });
  });

  test("2xx com usuário: entrou", async () => {
    responder({ doBackend: true, status: 201, corpo: ANA });
    assert.deepEqual(await enviarConta("/api/auth/cadastro", {}), { ok: true, usuario: ANA });
  });

  test("2xx com corpo que não é usuário não conta como sucesso", async () => {
    // Resposta inesperada não é culpa do que a pessoa digitou: a mensagem é a de sempre.
    responder({ doBackend: true, status: 200, corpo: { nome: "Ana" } });
    assert.deepEqual(await enviarConta("/api/auth/login", {}), {
      ok: false,
      mensagem: MENSAGEM_SEM_SERVIDOR,
    });
  });

  test("`detail` em texto é a frase do backend, mostrada como veio", async () => {
    responder({ doBackend: true, status: 409, corpo: { detail: "Este e-mail já tem conta." } });
    assert.deepEqual(await enviarConta("/api/auth/cadastro", {}), {
      ok: false,
      mensagem: "Este e-mail já tem conta.",
    });
  });

  test("422 em lista do FastAPI não serve para exibir: pede para conferir", async () => {
    responder({ doBackend: true, status: 422, corpo: { detail: [{ loc: ["body"], msg: "x" }] } });
    assert.deepEqual(await enviarConta("/api/auth/login", {}), { ok: false, mensagem: CONFIRA });
  });

  test("4xx sem `detail`: pede para conferir", async () => {
    responder({ doBackend: true, status: 400, corpo: {} });
    assert.deepEqual(await enviarConta("/api/auth/login", {}), { ok: false, mensagem: CONFIRA });
  });

  test("5xx sem `detail` e sem backend: a mensagem de sempre", async () => {
    responder({ doBackend: true, status: 500, corpo: {} });
    assert.deepEqual(await enviarConta("/api/auth/login", {}), {
      ok: false,
      mensagem: MENSAGEM_SEM_SERVIDOR,
    });
    responder({ doBackend: false });
    assert.deepEqual(await enviarConta("/api/auth/login", {}), {
      ok: false,
      mensagem: MENSAGEM_SEM_SERVIDOR,
    });
  });
});

describe("consultarSessao: quem está logado", () => {
  test("logado com usuário válido", async () => {
    vi.mocked(lerSessao).mockResolvedValue({ situacao: "logado", corpo: ANA });
    assert.deepEqual(await consultarSessao(), { situacao: "logado", usuario: ANA });
  });

  test("logado com corpo estranho vira erro, nunca um usuário inventado", async () => {
    vi.mocked(lerSessao).mockResolvedValue({ situacao: "logado", corpo: { email: 1 } });
    assert.deepEqual(await consultarSessao(), { situacao: "erro" });
  });

  test("só o 401 é deslogado; backend indisponível é 'não deu para saber'", async () => {
    vi.mocked(lerSessao).mockResolvedValue({ situacao: "deslogado" });
    assert.deepEqual(await consultarSessao(), { situacao: "deslogado" });
    vi.mocked(lerSessao).mockResolvedValue({ situacao: "indisponivel" });
    assert.deepEqual(await consultarSessao(), { situacao: "erro" });
  });
});

describe("sairDaConta: só diz que saiu quando o backend respondeu", () => {
  test("204: saiu", async () => {
    responder({ doBackend: true, status: 204, corpo: null });
    assert.equal(await sairDaConta(), true);
    assert.equal(vi.mocked(enviarUmaVez).mock.calls[0][1].method, "POST");
  });

  test("503 com `detail`: o backend limpou o cookie mesmo assim", async () => {
    responder({ doBackend: true, status: 503, corpo: { detail: "O serviço está iniciando." } });
    assert.equal(await sairDaConta(), true);
  });

  test("resposta do backend sem `detail` e fora do 204: não saiu", async () => {
    responder({ doBackend: true, status: 500, corpo: {} });
    assert.equal(await sairDaConta(), false);
  });

  test("sem resposta do backend o cookie continua valendo: não saiu", async () => {
    responder({ doBackend: false });
    assert.equal(await sairDaConta(), false);
  });
});
