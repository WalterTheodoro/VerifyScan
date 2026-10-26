// Testes da espera pelo backend (ADR-0017), no `node:test` do próprio Node: roda o .ts direto
// (type stripping), sem dependência nova. `fetch` e relógio são falsos — nenhuma chamada de rede.
//
//   npm test

import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, mock, test } from "node:test";

import {
  aquecer,
  enviarUmaVez,
  esquecerBackend,
  JANELA_ACORDADO_MS,
  LIMITE_ESPERA_MS,
  lerComRepeticao,
  lerSessao,
  pedir,
} from "./servidor.ts";

type Chamada = { caminho: string; metodo: string };

let chamadas: Chamada[] = [];

/** Troca o `fetch` global por um que responde conforme `responder`. Lançar = falha de rede. */
function fingirFetch(responder: (chamada: Chamada, ordem: number) => Response) {
  globalThis.fetch = async (entrada: string | URL | Request, init?: RequestInit) => {
    const chamada = { caminho: String(entrada), metodo: init?.method ?? "GET" };
    chamadas.push(chamada);
    return responder(chamada, chamadas.length);
  };
}

const json = (status: number, corpo: unknown) =>
  new Response(JSON.stringify(corpo), { status, headers: { "Content-Type": "application/json" } });

// O que o proxy do Next (ou o Render) devolve quando o backend não responde.
const html = (status: number) =>
  new Response("<!DOCTYPE html><html><body>erro</body></html>", {
    status,
    headers: { "Content-Type": "text/html" },
  });

const semRede = (): Response => {
  throw new TypeError("fetch failed");
};

/** Deixa rodar as promessas pendentes. `setImmediate` não é falsificado, `setTimeout` é. */
const esvaziar = () => new Promise((resolver) => setImmediate(resolver));

/** Avança o relógio falso em passos de até 500 ms, deixando as promessas andarem entre eles. */
async function avancar(ms: number) {
  for (let falta = ms; falta > 0; falta -= 500) {
    await esvaziar();
    mock.timers.tick(Math.min(500, falta));
  }
  await esvaziar();
}

const metodo = (m: string) => chamadas.filter((c) => c.metodo === m).length;
const aoCaminho = (caminho: string) => chamadas.filter((c) => c.caminho === caminho).length;

beforeEach(() => {
  chamadas = [];
  esquecerBackend();
  mock.timers.enable({ apis: ["setTimeout", "Date"], now: 0 });
});

afterEach(() => {
  mock.timers.reset();
});

describe("classificação: veio do backend ou de outra coisa", () => {
  const casos: [string, () => Response, boolean][] = [
    ["200 com JSON", () => json(200, { nome: "Ana", email: "a@b.c" }), true],
    ["401 com detail", () => json(401, { detail: "Não autenticado." }), true],
    ["503 com detail", () => json(503, { detail: "O serviço está iniciando." }), true],
    ["204 sem corpo", () => new Response(null, { status: 204 }), true],
    ["502 em HTML", () => html(502), false],
    ["404 em HTML", () => html(404), false],
    ["200 em HTML", () => html(200), false],
    ["falha de rede", semRede, false],
  ];

  for (const [nome, resposta, doBackend] of casos) {
    test(nome, async () => {
      fingirFetch(resposta);
      assert.equal((await pedir("/api/auth/eu")).doBackend, doBackend);
    });
  }

  test("guarda status e corpo do backend", async () => {
    fingirFetch(() => json(409, { detail: "Já existe uma conta com este e-mail." }));
    assert.deepEqual(await pedir("/api/auth/cadastro", { method: "POST" }), {
      doBackend: true,
      status: 409,
      corpo: { detail: "Já existe uma conta com este e-mail." },
    });
  });
});

describe("leituras repetem sozinhas", () => {
  test("sem resposta do backend, repete em 2, 3, 5, 5… s e para no limite", async () => {
    fingirFetch(() => html(502));
    let avisos = 0;
    let fim: { doBackend: boolean } | null = null;
    void lerComRepeticao("/api/historico", { aoEsperar: () => avisos++ }).then((r) => {
      fim = r;
    });

    await avancar(1999);
    assert.equal(chamadas.length, 1, "a primeira sai na hora");
    assert.equal(avisos, 1, "o aviso aparece já na primeira repetição");
    await avancar(1);
    assert.equal(chamadas.length, 2, "2 s");
    await avancar(3000);
    assert.equal(chamadas.length, 3, "+3 s");
    await avancar(5000);
    assert.equal(chamadas.length, 4, "+5 s");
    await avancar(5000);
    assert.equal(chamadas.length, 5, "+5 s de novo");

    await avancar(LIMITE_ESPERA_MS);
    // 0, 2, 5 e depois de 10 a 90 s de 5 em 5: 3 + 17.
    assert.equal(chamadas.length, 20);
    assert.deepEqual(fim, { doBackend: false });
    assert.equal(avisos, 1);
  });

  test("para assim que o backend responde", async () => {
    fingirFetch((_, ordem) => (ordem < 3 ? semRede() : json(200, { dias: 7, analises: [] })));
    let fim: unknown = null;
    void lerComRepeticao("/api/historico").then((r) => {
      fim = r;
    });
    await avancar(30_000);
    assert.equal(chamadas.length, 3);
    assert.deepEqual(fim, { doBackend: true, status: 200, corpo: { dias: 7, analises: [] } });
  });

  test("resposta de erro do backend não é repetida", async () => {
    fingirFetch(() => json(404, { detail: "Análise não encontrada." }));
    await lerComRepeticao("/api/historico");
    assert.equal(chamadas.length, 1);
  });

  test("para quando a tela sai (signal abortado)", async () => {
    fingirFetch(() => html(502));
    const controle = new AbortController();
    void lerComRepeticao("/api/historico", { signal: controle.signal });
    await avancar(2500);
    assert.equal(chamadas.length, 2);
    controle.abort();
    await avancar(LIMITE_ESPERA_MS);
    assert.equal(chamadas.length, 2);
  });
});

describe("sessão", () => {
  test("401 é deslogado, sem repetir", async () => {
    fingirFetch(() => json(401, { detail: "Não autenticado." }));
    assert.deepEqual(await lerSessao(), { situacao: "deslogado" });
    assert.equal(chamadas.length, 1);
  });

  test("503 com detail (banco acordando) repete até o 200", async () => {
    fingirFetch((_, ordem) =>
      ordem < 3 ? json(503, { detail: "O serviço está iniciando." }) : json(200, { nome: "Ana" }),
    );
    let fim: unknown = null;
    void lerSessao().then((r) => {
      fim = r;
    });
    await avancar(10_000);
    assert.equal(chamadas.length, 3);
    assert.deepEqual(fim, { situacao: "logado", corpo: { nome: "Ana" } });
  });

  test("esgotadas as tentativas, indisponível (não deslogado)", async () => {
    fingirFetch(semRede);
    let fim: unknown = null;
    void lerSessao().then((r) => {
      fim = r;
    });
    await avancar(LIMITE_ESPERA_MS + 5000);
    assert.deepEqual(fim, { situacao: "indisponivel" });
  });
});

describe("envios esperam pelo backend e saem uma vez", () => {
  test("backend dormindo: consulta /health até responder e faz o POST uma vez", async () => {
    let acordado = false;
    fingirFetch((chamada) => {
      if (chamada.caminho === "/health") {
        return acordado ? json(200, { status: "ok" }) : html(502);
      }
      return json(201, { nome: "Ana", email: "a@b.c" });
    });
    let avisos = 0;
    let fim: unknown = null;
    void enviarUmaVez("/api/auth/cadastro", { method: "POST" }, { aoEsperar: () => avisos++ }).then(
      (r) => {
        fim = r;
      },
    );

    await avancar(4000);
    assert.equal(metodo("POST"), 0, "não envia antes de o backend responder");
    assert.equal(avisos, 1);
    acordado = true;
    await avancar(10_000);

    assert.equal(metodo("POST"), 1);
    assert.deepEqual(fim, { doBackend: true, status: 201, corpo: { nome: "Ana", email: "a@b.c" } });
  });

  test("o POST que falha sem resposta não é repetido", async () => {
    fingirFetch((chamada) => (chamada.caminho === "/health" ? json(200, {}) : html(502)));
    let fim: unknown = null;
    void enviarUmaVez("/api/analises", { method: "POST" }).then((r) => {
      fim = r;
    });
    await avancar(LIMITE_ESPERA_MS);
    assert.equal(metodo("POST"), 1);
    assert.deepEqual(fim, { doBackend: false });
  });

  test("o /health não respondeu em 90 s: não envia", async () => {
    fingirFetch(() => html(502));
    let fim: unknown = null;
    void enviarUmaVez("/api/auth/login", { method: "POST" }).then((r) => {
      fim = r;
    });
    await avancar(LIMITE_ESPERA_MS + 5000);
    assert.equal(metodo("POST"), 0);
    assert.deepEqual(fim, { doBackend: false });
  });

  test("dentro da janela de acordado não consulta /health; fora dela, consulta", async () => {
    // O POST responde sem JSON para não renovar a janela: toda resposta do backend a renova, e
    // o que se mede aqui é o tempo desde a primeira.
    fingirFetch((chamada) => (chamada.metodo === "POST" ? html(502) : json(200, {})));
    await pedir("/api/auth/eu");

    await avancar(9 * 60_000);
    await enviarUmaVez("/api/analises", { method: "POST" });
    assert.equal(aoCaminho("/health"), 0, "9 min depois: ainda acordado");

    await avancar(2 * 60_000);
    assert.ok(11 * 60_000 > JANELA_ACORDADO_MS);
    await enviarUmaVez("/api/analises", { method: "POST" });
    assert.equal(aoCaminho("/health"), 1, "11 min depois: pode ter dormido");
    assert.equal(metodo("POST"), 2);
  });
});

describe("aquecimento", () => {
  test("uma requisição a /health por carregamento, e o envio aproveita a resposta", async () => {
    fingirFetch(() => json(200, { status: "ok" }));
    aquecer();
    aquecer();
    await esvaziar();
    assert.equal(aoCaminho("/health"), 1);

    await enviarUmaVez("/api/analises", { method: "POST" });
    assert.equal(aoCaminho("/health"), 1);
    assert.equal(metodo("POST"), 1);
  });
});
