// Repassa ao backend o IP do visitante, com o segredo compartilhado (fatia 10, ADR-0024).
//
// O Next 16 trocou o `middleware.ts` por este arquivo. Ele roda antes das rewrites do
// `next.config.ts` (ADR-0014): os cabeçalhos postos aqui, como cabeçalhos do PEDIDO
// (`NextResponse.next({ request: { headers } })`), seguem com o pedido reescrito para o backend.
// Como cabeçalhos da resposta, iriam para o navegador — e o segredo junto.
//
// `PROXY_SEGREDO` é lido em execução, não no build, ao contrário das rewrites. O `next.config.ts`
// recusa o build de produção sem ele.

import { NextResponse, type NextRequest } from "next/server";

import { cabecalhosParaOBackend } from "./app/_lib/ip";
import { comRequestId } from "./app/_lib/request-id";

export function proxy(request: NextRequest) {
  // O id da requisição nasce aqui e segue com o pedido: o backend o põe em todo log dela e o
  // devolve no cabeçalho da resposta (ADR-0026).
  const cabecalhos = comRequestId(
    cabecalhosParaOBackend(request.headers, process.env.PROXY_SEGREDO),
  );
  return NextResponse.next({ request: { headers: cabecalhos } });
}

// Só o que vai para o backend, os mesmos caminhos das rewrites. O /health não usa o IP, mas passa
// por aqui para nenhum `X-VerifyScan-*` do navegador chegar ao backend. Com um proxy, o Next guarda
// o corpo do pedido em memória (`proxyClientMaxBodySize`): limitar o matcher poupa disso as
// páginas e os arquivos estáticos.
export const config = {
  matcher: ["/api/:path*", "/health"],
};
