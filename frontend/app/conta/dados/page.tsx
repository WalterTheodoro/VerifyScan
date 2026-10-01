import type { Metadata } from "next";

import { DadosDaConta } from "./dados";

export const metadata: Metadata = { title: "Meus dados — Minha conta — VerifyScan" };

export default function PaginaDados() {
  return <DadosDaConta />;
}
