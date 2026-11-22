// Chamadas da área "Minha conta" (ADR-0015, ADR-0017): o histórico e os dados da conta. GET
// repete enquanto o backend acorda; DELETE espera e sai uma vez. A espera em si é testada em
// `servidor.test.ts`; aqui ela é falsa, e cada teste diz o que "chegou".
//
//   npm test

import assert from "node:assert/strict";
import { beforeEach, describe, test, vi } from "vitest";

import { MENSAGEM_SEM_SERVIDOR } from "./conta";
import {
  apagarAnalise,
  apagarHistorico,
  buscarConta,
  buscarHistorico,
  formatarData,
  formatarDataHora,
} from "./historico";
import { enviarUmaVez, lerComRepeticao } from "./servidor";

vi.mock("./servidor", () => ({ enviarUmaVez: vi.fn(), lerComRepeticao: vi.fn() }));

const HISTORICO = { dias: 7, analises: [] };
const CONTA = { nome: "Ana", email: "ana@exemplo.com", criado_em: "2026-10-01T12:00:00Z" };

beforeEach(() => {
  vi.mocked(enviarUmaVez).mockReset();
  vi.mocked(lerComRepeticao).mockReset();
});

describe("leituras: histórico e dados da conta", () => {
  test("histórico válido: ok, pela leitura que repete", async () => {
    vi.mocked(lerComRepeticao).mockResolvedValue({ doBackend: true, status: 200, corpo: HISTORICO });
    const opcoes = { aoEsperar: () => {} };
    assert.deepEqual(await buscarHistorico(opcoes), { situacao: "ok", dados: HISTORICO });
    assert.deepEqual(vi.mocked(lerComRepeticao).mock.calls[0], ["/api/historico", opcoes]);
    assert.equal(vi.mocked(enviarUmaVez).mock.calls.length, 0);
  });

  test("dados da conta válidos: ok", async () => {
    vi.mocked(lerComRepeticao).mockResolvedValue({ doBackend: true, status: 200, corpo: CONTA });
    assert.deepEqual(await buscarConta({}), { situacao: "ok", dados: CONTA });
    assert.equal(vi.mocked(lerComRepeticao).mock.calls[0][0], "/api/conta");
  });

  test("401: a sessão venceu com a página aberta", async () => {
    vi.mocked(lerComRepeticao).mockResolvedValue({ doBackend: true, status: 401, corpo: {} });
    assert.deepEqual(await buscarHistorico({}), { situacao: "deslogado" });
  });

  test("2xx com corpo de outro formato vira erro, nunca uma tela com dado faltando", async () => {
    vi.mocked(lerComRepeticao).mockResolvedValue({
      doBackend: true,
      status: 200,
      corpo: { dias: "7", analises: [] },
    });
    assert.deepEqual(await buscarHistorico({}), {
      situacao: "erro",
      mensagem: MENSAGEM_SEM_SERVIDOR,
    });
    vi.mocked(lerComRepeticao).mockResolvedValue({
      doBackend: true,
      status: 200,
      corpo: { nome: "Ana", email: "ana@exemplo.com" },
    });
    assert.equal((await buscarConta({})).situacao, "erro");
  });

  test("`detail` em texto é a frase mostrada", async () => {
    vi.mocked(lerComRepeticao).mockResolvedValue({
      doBackend: true,
      status: 503,
      corpo: { detail: "O serviço está iniciando." },
    });
    assert.deepEqual(await buscarConta({}), {
      situacao: "erro",
      mensagem: "O serviço está iniciando.",
    });
  });

  test("sem resposta do backend: a mensagem de sempre", async () => {
    vi.mocked(lerComRepeticao).mockResolvedValue({ doBackend: false });
    assert.deepEqual(await buscarHistorico({}), {
      situacao: "erro",
      mensagem: MENSAGEM_SEM_SERVIDOR,
    });
  });
});

describe("apagar: espera o backend e sai uma vez", () => {
  test("apagar uma análise: DELETE no id, escapado", async () => {
    vi.mocked(enviarUmaVez).mockResolvedValue({ doBackend: true, status: 204, corpo: null });
    assert.deepEqual(await apagarAnalise("a/b c"), { situacao: "ok", dados: true });
    const [caminho, init] = vi.mocked(enviarUmaVez).mock.calls[0];
    assert.equal(caminho, "/api/historico/a%2Fb%20c");
    assert.equal(init.method, "DELETE");
    assert.equal(vi.mocked(lerComRepeticao).mock.calls.length, 0);
  });

  test("apagar o histórico inteiro", async () => {
    vi.mocked(enviarUmaVez).mockResolvedValue({ doBackend: true, status: 204, corpo: null });
    assert.deepEqual(await apagarHistorico(), { situacao: "ok", dados: true });
    assert.equal(vi.mocked(enviarUmaVez).mock.calls[0][0], "/api/historico");
  });

  test("404 com `detail`: a frase do backend", async () => {
    vi.mocked(enviarUmaVez).mockResolvedValue({
      doBackend: true,
      status: 404,
      corpo: { detail: "Análise não encontrada." },
    });
    assert.deepEqual(await apagarAnalise("x"), {
      situacao: "erro",
      mensagem: "Análise não encontrada.",
    });
  });
});

describe("datas no fuso de São Paulo, qualquer que seja o do navegador", () => {
  test("02:30 UTC ainda é o dia anterior no Brasil", () => {
    assert.equal(formatarData("2026-10-02T02:30:00Z"), "01/10/2026");
    assert.equal(formatarDataHora("2026-10-02T02:30:00Z"), "01/10/2026 às 23:30");
  });

  test("hora com dois dígitos", () => {
    assert.equal(formatarDataHora("2026-10-01T12:05:00Z"), "01/10/2026 às 09:05");
  });
});
