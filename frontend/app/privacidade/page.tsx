import type { Metadata } from "next";

import { AvisoPrivacidade } from "../_componentes/aviso-privacidade";
import { Cabecalho } from "../_componentes/cabecalho";
import { Rodape } from "../_componentes/rodape";
import { RaizDaPagina } from "../_componentes/raiz-da-pagina";

export const metadata: Metadata = { title: "Aviso de privacidade — VerifyScan" };

/** Página pública, para quem ainda não tem conta (link do rodapé e do cadastro). O conteúdo é o
 *  mesmo da seção Privacidade da conta: um componente só. */
export default function PaginaPrivacidade() {
  return (
    <RaizDaPagina>
      <Cabecalho />
      <main className="fundo-hero flex-1">
        <div className="mx-auto flex w-full max-w-[44rem] flex-col gap-bloco px-5 pb-secao
          pt-bloco">
          <h1 className="text-titulo font-bold sm:text-titulo-lg">Aviso de privacidade</h1>
          <div className="cartao p-5 sm:p-bloco">
            <AvisoPrivacidade nivel="h2" />
          </div>
        </div>
      </main>
      <Rodape />
    </RaizDaPagina>
  );
}
