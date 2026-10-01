import { useEffect, useState } from "react";

import type { Resultado } from "./historico";
import { ESPERA_ATE_AVISAR_MS } from "./use-envio-conta";

export type Carga<T> = Resultado<T> | { situacao: "carregando" };

/** Busca uma vez ao montar, com o aviso de "servidor acordando" depois de 5 s.
 *
 *  `buscar` precisa ser estável (função de módulo), senão o efeito repetiria a busca a cada
 *  renderização. `definir` deixa a tela atualizar o que já carregou — apagar um item, por
 *  exemplo — sem buscar de novo. */
export function useCarga<T>(buscar: () => Promise<Resultado<T>>) {
  const [carga, definir] = useState<Carga<T>>({ situacao: "carregando" });
  const [demorando, setDemorando] = useState(false);

  useEffect(() => {
    // setState só nos callbacks, nunca no corpo do efeito (react-hooks/set-state-in-effect); a
    // flag `ativo` descarta a resposta que chegar depois de a página sair da tela.
    let ativo = true;
    const timer = window.setTimeout(() => setDemorando(true), ESPERA_ATE_AVISAR_MS);
    void buscar().then((resultado) => {
      window.clearTimeout(timer);
      if (ativo) {
        setDemorando(false);
        definir(resultado);
      }
    });
    return () => {
      ativo = false;
      window.clearTimeout(timer);
    };
  }, [buscar]);

  return { carga, definir, demorando };
}
