// Sentry no navegador (ADR-0026). O Next carrega este arquivo antes de a página ficar interativa.
//
// Ligado só com NEXT_PUBLIC_SENTRY_DSN: sem a variável, o `init` nem é chamado. O que é enviado e
// o que nunca é está em `app/_lib/sentry.ts`. Sem Session Replay: nenhuma integração é
// acrescentada aqui, e o Replay não está nas integrações padrão do SDK. Das padrão, saem a
// contagem de sessões e o idioma e fuso do navegador (`INTEGRACOES_DESLIGADAS`).

import * as Sentry from "@sentry/nextjs";

import { opcoesDoNavegador } from "./app/_lib/sentry";

const opcoes = opcoesDoNavegador(
  process.env.NEXT_PUBLIC_SENTRY_DSN,
  process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT,
);

if (opcoes) {
  Sentry.init(opcoes);
}

// O Next chama esta função a cada troca de página; o SDK a usa para medir a navegação. Sem o
// `init`, ela não faz nada.
export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
