// O túnel do Sentry (ADR-0026): o navegador manda o evento para o nosso domínio, e esta rota o
// reenvia ao Sentry. Assim o navegador nunca fala com o Sentry, e bloqueador de anúncio não
// barra o envio.
//
// O nome da pasta é o que o SDK procura (`app/sentry-tunnel/route.ts`); o endereço público é o
// `CAMINHO_DO_TUNEL`, que o `withSentryConfig` do `next.config.ts` reescreve para cá.
//
// A função do SDK repassaria ao Sentry o IP do visitante, que ela lê do `x-forwarded-for`. Por
// isso o pedido passa antes pelo `pedidoSemIp`: o Sentry só vê o endereço do nosso servidor.
//
// Só reenvia evento do NOSSO projeto (`allowedDsns`): sem isso, a rota seria um repassador
// aberto para qualquer projeto do Sentry.

import { createSentryTunnelRoute } from "@sentry/nextjs/tunnel";

import { pedidoSemIp } from "../_lib/sentry";

const DSN = process.env.NEXT_PUBLIC_SENTRY_DSN?.trim();
const tunel = DSN ? createSentryTunnelRoute({ allowedDsns: [DSN] }) : null;

export async function POST(pedido: Request): Promise<Response> {
  // Sem DSN não há Sentry: a rota responde como se não existisse.
  if (!tunel) {
    return new Response(null, { status: 404 });
  }
  return tunel.POST(pedidoSemIp(pedido));
}
