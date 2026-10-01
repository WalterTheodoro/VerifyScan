import type { Metadata } from "next";

import { Cabecalho } from "../_componentes/cabecalho";
import { Rodape } from "../_componentes/rodape";
import { RaizDaPagina } from "../_componentes/raiz-da-pagina";
import { FormularioEntrar } from "./formulario";

export const metadata: Metadata = { title: "Entrar — VerifyScan" };

export default function PaginaEntrar() {
  return (
    <RaizDaPagina>
      <Cabecalho />
      <main className="fundo-hero flex-1">
        <div className="mx-auto flex w-full max-w-[34rem] flex-col gap-bloco px-5 pb-secao
          pt-bloco">
          <h1 className="text-titulo font-bold sm:text-titulo-lg">Entrar na sua conta</h1>
          <FormularioEntrar />
        </div>
      </main>
      <Rodape />
    </RaizDaPagina>
  );
}
