// @vitest-environment jsdom
// O envio das telas de conta: estado de envio, aviso de demora aos 5 s (ou antes, se o backend
// estiver acordando), erro com foco nele, e a ida para a home depois de entrar ou se cadastrar.
//
//   npm test

import assert from "node:assert/strict";
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, test, vi } from "vitest";

import { enviarConta, type ResultadoConta } from "./conta";
import type { OpcoesDeEspera } from "./servidor";
import { ESPERA_ATE_AVISAR_MS, useEnvio, useEnvioConta } from "./use-envio-conta";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("./conta", () => ({ enviarConta: vi.fn() }));

beforeEach(() => {
  vi.useFakeTimers();
  push.mockReset();
  vi.mocked(enviarConta).mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

/** Uma ação que só termina quando o teste manda. */
function acaoManual<T>() {
  let terminar: (valor: T) => void = () => {};
  let opcoes: OpcoesDeEspera = {};
  const acao = (recebidas: OpcoesDeEspera) => {
    opcoes = recebidas;
    return new Promise<T>((resolver) => {
      terminar = resolver;
    });
  };
  return { acao, terminar: (valor: T) => terminar(valor), opcoes: () => opcoes };
}

describe("useEnvio", () => {
  test("enquanto envia: botão em 'enviando', sem erro; o aviso de demora sai aos 5 s", async () => {
    const { result } = renderHook(() => useEnvio());
    const manual = acaoManual<string>();
    let promessa: Promise<string> = Promise.resolve("");
    act(() => {
      promessa = result.current.enviar(manual.acao);
    });
    assert.equal(result.current.enviando, true);
    assert.equal(result.current.erro, null);
    assert.equal(result.current.demorando, false);

    act(() => vi.advanceTimersByTime(ESPERA_ATE_AVISAR_MS));
    assert.equal(result.current.demorando, true);

    await act(async () => {
      manual.terminar("feito");
      assert.equal(await promessa, "feito");
    });
    // O aviso some, mas o botão segue "enviando" até a tela decidir.
    assert.equal(result.current.demorando, false);
    assert.equal(result.current.enviando, true);
    act(() => result.current.concluir());
    assert.equal(result.current.enviando, false);
  });

  test("backend acordando: o aviso liga antes dos 5 s", () => {
    const { result } = renderHook(() => useEnvio());
    const manual = acaoManual<void>();
    act(() => {
      void result.current.enviar(manual.acao);
    });
    act(() => manual.opcoes().aoEsperar?.());
    assert.equal(result.current.demorando, true);
  });

  test("falhar: mostra o erro, libera o botão e leva o foco ao aviso", () => {
    const { result } = renderHook(() => useEnvio());
    const aviso = document.createElement("div");
    aviso.tabIndex = -1;
    document.body.append(aviso);
    result.current.avisoDeErro.current = aviso;

    act(() => result.current.falhar("Senha incorreta."));
    assert.equal(result.current.erro, "Senha incorreta.");
    assert.equal(result.current.enviando, false);
    act(() => vi.runAllTimers()); // o requestAnimationFrame do foco
    assert.equal(document.activeElement, aviso);
    aviso.remove();
  });

  test("um novo envio limpa o erro anterior", () => {
    const { result } = renderHook(() => useEnvio());
    act(() => result.current.falhar("Erro antigo."));
    act(() => {
      void result.current.enviar(acaoManual<void>().acao);
    });
    assert.equal(result.current.erro, null);
  });
});

describe("useEnvioConta", () => {
  async function enviarCom(resultado: ResultadoConta) {
    vi.mocked(enviarConta).mockResolvedValue(resultado);
    const { result } = renderHook(() => useEnvioConta("/api/auth/login"));
    await act(async () => {
      result.current.enviar({ email: "ana@exemplo.com", senha: "x" });
    });
    return result;
  }

  test("entrou: vai para a home, e o botão continua 'Entrando…'", async () => {
    const result = await enviarCom({ ok: true, usuario: { nome: "Ana", email: "a@b.c" } });
    assert.deepEqual(push.mock.calls, [["/"]]);
    assert.equal(result.current.enviando, true);
    assert.equal(result.current.erro, null);
    const [caminho, corpo] = vi.mocked(enviarConta).mock.calls[0];
    assert.equal(caminho, "/api/auth/login");
    assert.deepEqual(corpo, { email: "ana@exemplo.com", senha: "x" });
  });

  test("não entrou: fica na tela, com a frase do backend", async () => {
    const result = await enviarCom({ ok: false, mensagem: "E-mail ou senha incorretos." });
    assert.equal(push.mock.calls.length, 0);
    assert.equal(result.current.erro, "E-mail ou senha incorretos.");
    assert.equal(result.current.enviando, false);
  });
});
