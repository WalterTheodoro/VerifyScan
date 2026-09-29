import type { Metadata } from "next";
import { Atkinson_Hyperlegible_Mono, Atkinson_Hyperlegible_Next } from "next/font/google";
import "./globals.css";

// Atkinson Hyperlegible foi desenhada pelo Braille Institute para leitores com baixa visão:
// distingue I/l/1 e O/0. A versão Mono é usada só nos links, onde conferir caractere a
// caractere é justamente a tarefa (um domínio falso vive de trocar "l" por "1").
const textoLegivel = Atkinson_Hyperlegible_Next({
  subsets: ["latin", "latin-ext"],
  variable: "--fonte-texto",
});

const monoLegivel = Atkinson_Hyperlegible_Mono({
  subsets: ["latin", "latin-ext"],
  variable: "--fonte-mono",
});

export const metadata: Metadata = {
  title: "VerifyScan",
  description:
    "Analise mensagens suspeitas e descubra o nível de risco, os fatores identificados e o que fazer.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="pt-BR"
      className={`${textoLegivel.variable} ${monoLegivel.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
