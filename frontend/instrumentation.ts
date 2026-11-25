// Sentry no servidor do Next (ADR-0026). O Next chama `register` uma vez, quando o servidor sobe.
//
// Ligado só com NEXT_PUBLIC_SENTRY_DSN, a mesma variável do navegador: é um projeto só no Sentry.
// As opções e a limpeza dos eventos são as de `app/_lib/sentry.ts`.

import * as Sentry from "@sentry/nextjs";

import { integracoesDoServidor, OPCOES_DO_HTTP_NO_SERVIDOR, opcoesDoSentry } from "./app/_lib/sentry";

export function register() {
  const opcoes = opcoesDoSentry(
    process.env.NEXT_PUBLIC_SENTRY_DSN,
    process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT,
  );
  if (!opcoes) {
    return;
  }
  if (process.env.NEXT_RUNTIME === "nodejs") {
    Sentry.init({
      ...opcoes,
      // O servidor do Next repassa /api/* ao backend, e o corpo desses pedidos é a mensagem ou o
      // print da pessoa: a Http não guarda corpo. Sem contagem de sessões, nem por processo nem
      // por requisição (ADR-0026, revisão).
      integrations: (padrao) =>
        integracoesDoServidor(padrao, Sentry.httpIntegration(OPCOES_DO_HTTP_NO_SERVIDOR)),
    });
  } else {
    // O runtime "edge" não tem a integração de HTTP do Node, não lê o corpo dos pedidos e não
    // conta sessões.
    Sentry.init(opcoes);
  }
}

// Erros de renderização no servidor (páginas e rotas). Sem o `init`, não envia nada.
export const onRequestError = Sentry.captureRequestError;
