import type { RefObject } from "react";

/** Região `aria-live` das telas de conta: o aviso de demora e o erro do backend.
 *
 *  Sempre montada, mesmo vazia — região criada junto com o conteúdo não é anunciada por alguns
 *  leitores de tela (a mesma lição da tela de análise). */
export function AvisosDoEnvio({
  demorando,
  erro,
  avisoDeErro,
}: {
  demorando: boolean;
  erro: string | null;
  avisoDeErro: RefObject<HTMLDivElement | null>;
}) {
  return (
    <div aria-live="polite" className="flex flex-col gap-perto">
      {demorando && (
        <p className="font-semibold">O servidor está acordando. Isso pode levar até 1 minuto.</p>
      )}
      {erro && (
        // `tabIndex={-1}`: recebe o foco por código, sem entrar na ordem do Tab.
        <div ref={avisoDeErro} tabIndex={-1} role="alert"
          className="rounded-2xl border-2 border-l-[10px] border-[var(--erro)] bg-papel p-5">
          <p>{erro}</p>
        </div>
      )}
    </div>
  );
}
