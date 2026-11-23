"use client";

// Página de erro global (ADR-0026). O Next a mostra quando um erro escapa de tudo, inclusive do
// layout raiz; por isso ela traz o próprio <html> e <body>.
//
// Reporta o erro ao Sentry (sem DSN, a chamada não envia nada) e mostra uma mensagem simples. O
// texto do erro nunca aparece na tela: é técnico, e pode citar o que a pessoa digitou.

import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";

import "./globals.css";

export default function ErroGlobal({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="pt-BR">
      <body className="min-h-full flex flex-col">
        <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-bloco p-6">
          <h1 className="text-secao font-bold sm:text-secao-lg">Algo deu errado</h1>
          <p className="text-destaque">
            Tivemos um problema ao mostrar esta página. Não foi nada que você fez.
          </p>
          <p className="text-destaque">
            Toque em &ldquo;Tentar de novo&rdquo;. Se continuar, feche a página e abra outra vez.
          </p>
          <button
            type="button"
            onClick={reset}
            className="botao-principal alvo-de-toque self-start rounded-full px-8 py-3"
          >
            Tentar de novo
          </button>
        </main>
      </body>
    </html>
  );
}
