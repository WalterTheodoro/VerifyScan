import type { ReactNode } from "react";

import { Cabecalho } from "../_componentes/cabecalho";
import { RaizDaPagina } from "../_componentes/raiz-da-pagina";
import { Rodape } from "../_componentes/rodape";
import { MenuConta } from "./menu";
import { Porteiro } from "./porteiro";

/** Moldura da área "Minha conta": cabeçalho, menu, painel e rodapé (ADR-0016).
 *
 *  É layout, e não página: ao trocar de seção só o painel muda; o menu, o cabeçalho e a sessão
 *  já consultada ficam. Cada seção é uma rota com URL própria, então o voltar do navegador
 *  funciona sem JavaScript de abas. */
export default function LayoutConta({ children }: { children: ReactNode }) {
  return (
    <RaizDaPagina>
      <Cabecalho />
      <main className="fundo-hero flex-1">
        <div className="mx-auto flex w-full max-w-[60rem] flex-col gap-bloco px-5 pb-secao
          pt-bloco">
          <h1 className="text-titulo font-bold sm:text-titulo-lg">Minha conta</h1>
          {/* A partir de 768 px: menu em coluna fixa à esquerda, painel à direita. */}
          <div className="flex flex-col gap-bloco md:grid md:grid-cols-[14rem_minmax(0,1fr)]
            md:items-start">
            <MenuConta />
            <div className="cartao min-w-0 p-5 sm:p-bloco">
              <Porteiro>{children}</Porteiro>
            </div>
          </div>
        </div>
      </main>
      <Rodape />
    </RaizDaPagina>
  );
}
