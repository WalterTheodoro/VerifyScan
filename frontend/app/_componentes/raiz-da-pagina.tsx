import type { ReactNode } from "react";

/** Elemento único na raiz de cada página com cabeçalho.
 *
 *  O Next 16 decide a rolagem ao navegar medindo o Fragment da página. Com cabeçalho fixo
 *  (sticky) como primeiro filho e rodapé como último, ele achava a página "fora da tela" e
 *  chamava `scrollIntoView` em cada filho, do último ao primeiro: o rodapé levava ao fim da
 *  página. Com um só elemento em fluxo na raiz, ela abre no topo. */
export function RaizDaPagina({ children }: { children: ReactNode }) {
  return <div className="flex flex-1 flex-col">{children}</div>;
}
