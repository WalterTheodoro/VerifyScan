import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VerifyScan",
  description:
    "Analise mensagens suspeitas e descubra o nível de risco, os fatores identificados e o que fazer.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="pt-BR" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
