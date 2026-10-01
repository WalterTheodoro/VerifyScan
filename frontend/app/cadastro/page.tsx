import type { Metadata } from "next";

import { Cabecalho } from "../_componentes/cabecalho";
import { Rodape } from "../_componentes/rodape";
import { RaizDaPagina } from "../_componentes/raiz-da-pagina";
import { FormularioCadastro } from "./formulario";

export const metadata: Metadata = { title: "Criar conta — VerifyScan" };

export default function PaginaCadastro() {
  return (
    <RaizDaPagina>
      <Cabecalho />
      <main className="fundo-hero flex-1">
        <div className="mx-auto flex w-full max-w-[34rem] flex-col gap-bloco px-5 pb-secao
          pt-bloco">
          <div className="flex flex-col gap-perto">
            <h1 className="text-titulo font-bold sm:text-titulo-lg">Criar sua conta</h1>
            {/* Verdade e não convite: a análise continua aberta a quem não tem conta. */}
            <p className="text-destaque">A conta é opcional. A análise funciona sem ela.</p>
          </div>
          <FormularioCadastro />
        </div>
      </main>
      <Rodape />
    </RaizDaPagina>
  );
}
