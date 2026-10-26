import { useEffect, useState } from "react";

import type { Resultado } from "./historico";
import type { OpcoesDeEspera } from "./servidor";
import { ESPERA_ATE_AVISAR_MS } from "./use-envio-conta";

export type Carga<T> = Resultado<T> | { situacao: "carregando" };

/** Busca uma vez ao montar. O aviso de "servidor acordando" aparece quando a busca começa a
 *  repetir (ADR-0017) ou depois de 5 s sem resposta, o que vier primeiro.
 *
 *  `buscar` precisa ser estável (função de módulo), senão o efeito repetiria a busca a cada
 *  renderização. `definir` deixa a tela atualizar o que já carregou — apagar um item, por
 *  exemplo — sem buscar de novo. */
export function useCarga<T>(buscar: (opcoes: OpcoesDeEspera) => Promise<Resultado<T>>) {
  const [carga, definir] = useState<Carga<T>>({ situacao: "carregando" });
  const [demorando, setDemorando] = useState(false);

  useEffect(() => {
    // setState só nos callbacks, nunca no corpo do efeito (react-hooks/set-state-in-effect). O
    // abort para as tentativas e descarta a resposta que chegar depois de a página sair da tela.
    const controle = new AbortController();
    const timer = window.setTimeout(() => setDemorando(true), ESPERA_ATE_AVISAR_MS);
    void buscar({ aoEsperar: () => setDemorando(true), signal: controle.signal }).then(
      (resultado) => {
        window.clearTimeout(timer);
        if (!controle.signal.aborted) {
          setDemorando(false);
          definir(resultado);
        }
      },
    );
    return () => {
      controle.abort();
      window.clearTimeout(timer);
    };
  }, [buscar]);

  return { carga, definir, demorando };
}
