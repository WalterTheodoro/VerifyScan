// @vitest-environment jsdom
// A carga das telas da conta (ADR-0017): busca uma vez ao montar, avisa que o servidor está
// acordando — quando a busca começa a repetir ou depois de 5 s —, e descarta a resposta que chega
// depois de a tela sair.
//
//   npm test

import assert from "node:assert/strict";
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, test, vi } from "vitest";

import type { Resultado } from "./historico";
import type { OpcoesDeEspera } from "./servidor";
import { useCarga } from "./use-carga";
import { ESPERA_ATE_AVISAR_MS } from "./use-envio-conta";

// `use-carga` importa o prazo do aviso de `use-envio-conta`, que importa o roteador do Next.
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

/** Uma busca que só responde quando o teste manda, e guarda as opções que recebeu. */
function buscaManual() {
  let responder: (resultado: Resultado<string>) => void = () => {};
  let opcoes: OpcoesDeEspera = {};
  const buscar = vi.fn((recebidas: OpcoesDeEspera) => {
    opcoes = recebidas;
    return new Promise<Resultado<string>>((resolver) => {
      responder = resolver;
    });
  });
  return {
    buscar,
    responder: (resultado: Resultado<string>) => act(async () => responder(resultado)),
    opcoes: () => opcoes,
  };
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

test("começa carregando, busca uma vez e mostra o resultado", async () => {
  const busca = buscaManual();
  const { result, rerender } = renderHook(() => useCarga(busca.buscar));
  assert.deepEqual(result.current.carga, { situacao: "carregando" });
  rerender();
  assert.equal(busca.buscar.mock.calls.length, 1);

  await busca.responder({ situacao: "ok", dados: "pronto" });
  assert.deepEqual(result.current.carga, { situacao: "ok", dados: "pronto" });
  assert.equal(result.current.demorando, false);
});

test("o aviso de demora aparece aos 5 s sem resposta, e some quando ela chega", async () => {
  const busca = buscaManual();
  const { result } = renderHook(() => useCarga(busca.buscar));
  act(() => vi.advanceTimersByTime(ESPERA_ATE_AVISAR_MS - 1));
  assert.equal(result.current.demorando, false);
  act(() => vi.advanceTimersByTime(1));
  assert.equal(result.current.demorando, true);

  await busca.responder({ situacao: "deslogado" });
  assert.equal(result.current.demorando, false);
  assert.deepEqual(result.current.carga, { situacao: "deslogado" });
});

test("a busca que começa a repetir liga o aviso antes dos 5 s", () => {
  const busca = buscaManual();
  const { result } = renderHook(() => useCarga(busca.buscar));
  act(() => busca.opcoes().aoEsperar?.());
  assert.equal(result.current.demorando, true);
});

test("`definir` atualiza o que já carregou sem buscar de novo", async () => {
  const busca = buscaManual();
  const { result } = renderHook(() => useCarga(busca.buscar));
  await busca.responder({ situacao: "ok", dados: "a" });
  act(() => result.current.definir({ situacao: "ok", dados: "b" }));
  assert.deepEqual(result.current.carga, { situacao: "ok", dados: "b" });
  assert.equal(busca.buscar.mock.calls.length, 1);
});

test("saiu da tela: a busca é abortada e a resposta tardia é descartada", async () => {
  const busca = buscaManual();
  const { result, unmount } = renderHook(() => useCarga(busca.buscar));
  const sinal = busca.opcoes().signal;
  assert.ok(sinal);
  assert.equal(sinal.aborted, false);

  unmount();
  assert.equal(sinal.aborted, true);
  await busca.responder({ situacao: "ok", dados: "tarde demais" });
  assert.deepEqual(result.current.carga, { situacao: "carregando" });
  // O timer do aviso também foi desligado: avançar o relógio não muda nada.
  act(() => vi.advanceTimersByTime(ESPERA_ATE_AVISAR_MS));
  assert.equal(result.current.demorando, false);
});
