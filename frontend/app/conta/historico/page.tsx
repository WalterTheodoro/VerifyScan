import type { Metadata } from "next";

import { ListaDoHistorico } from "./lista";

export const metadata: Metadata = { title: "Histórico — Minha conta — VerifyScan" };

export default function PaginaHistorico() {
  return <ListaDoHistorico />;
}
