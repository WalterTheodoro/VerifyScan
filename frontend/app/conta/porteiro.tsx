"use client";

import { useRef, type ReactNode } from "react";

import { AvisosDoEnvio } from "../_componentes/avisos-do-envio";
import { MENSAGEM_SEM_SERVIDOR, verificarSessao } from "../_lib/conta";
import type { Resultado } from "../_lib/historico";
import { useCarga } from "../_lib/use-carga";
import { AvisoEntrar } from "./aviso-entrar";

/** `verificarSessao` no formato de `Resultado`, para reaproveitar o `useCarga`. De módulo, para
 *  ser estável entre renderizações. */
async function sessao(): Promise<Resultado<true>> {
  const situacao = await verificarSessao();
  if (situacao === "logado") {
    return { situacao: "ok", dados: true };
  }
  return situacao === "deslogado"
    ? { situacao: "deslogado" }
    : { situacao: "erro", mensagem: MENSAGEM_SEM_SERVIDOR };
}

/** Só mostra a seção para quem está logado. Fica no layout, que persiste entre as seções: a
 *  sessão é consultada uma vez ao entrar na área, não a cada troca de seção. */
export function Porteiro({ children }: { children: ReactNode }) {
  const { carga, demorando } = useCarga(sessao);
  const avisoDeErro = useRef<HTMLDivElement>(null);

  if (carga.situacao === "ok") {
    return children;
  }
  if (carga.situacao === "deslogado") {
    return <AvisoEntrar />;
  }
  return (
    <AvisosDoEnvio
      demorando={demorando}
      erro={carga.situacao === "erro" ? carga.mensagem : null}
      avisoDeErro={avisoDeErro}
    />
  );
}
