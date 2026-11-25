import type { Metadata } from "next";
import Link from "next/link";

import { Cabecalho } from "./_componentes/cabecalho";
import { RaizDaPagina } from "./_componentes/raiz-da-pagina";
import { Rodape } from "./_componentes/rodape";

export const metadata: Metadata = { title: "Página não encontrada — VerifyScan" };

/** O que o Next mostra para um endereço que não existe, no lugar da página padrão em inglês. O
 *  status continua 404; só muda o que a pessoa vê. */
export default function NaoEncontrada() {
  return (
    <RaizDaPagina>
      <Cabecalho />
      <main className="fundo-hero flex-1">
        <div className="mx-auto flex w-full max-w-[44rem] flex-col gap-bloco px-5 pb-secao
          pt-bloco">
          <h1 className="text-titulo font-bold sm:text-titulo-lg">Página não encontrada</h1>
          <div className="cartao flex flex-col gap-bloco p-5 sm:p-bloco">
            <p className="text-destaque">
              Este endereço não existe no VerifyScan. Confira se ele foi digitado certo, ou volte
              para o começo.
            </p>
            <Link
              href="/"
              className="botao-principal alvo-de-toque self-start rounded-full px-8 py-3
                font-bold"
            >
              Ir para a página inicial
            </Link>
          </div>
        </div>
      </main>
      <Rodape />
    </RaizDaPagina>
  );
}
