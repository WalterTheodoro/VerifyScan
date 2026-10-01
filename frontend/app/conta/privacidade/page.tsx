import type { Metadata } from "next";

import { AvisoPrivacidade } from "../../_componentes/aviso-privacidade";

export const metadata: Metadata = { title: "Privacidade — Minha conta — VerifyScan" };

/** O mesmo aviso da página pública /privacidade, dentro do painel da conta. */
export default function PaginaPrivacidadeDaConta() {
  return (
    <section aria-labelledby="titulo-privacidade" className="flex flex-col gap-bloco">
      <h2 id="titulo-privacidade" className="text-secao font-bold sm:text-secao-lg">
        Privacidade
      </h2>
      <AvisoPrivacidade nivel="h3" />
    </section>
  );
}
