import { withSentryConfig } from "@sentry/nextjs/config";
import type { NextConfig } from "next";

import { CAMINHO_DO_TUNEL } from "./app/_lib/sentry";

// O navegador fala só com o frontend, e o Next repassa /api/* e /health ao backend (ADR-0014).
// Assim o cookie de sessão fica first-party no domínio do frontend: onrender.com está na Public
// Suffix List, e um cookie do backend seria de terceiro — o Safari bloqueia (ADR-0013).
//
// Variável de servidor, sem NEXT_PUBLIC_: o navegador nunca precisa saber onde o backend mora
// (exceto o despertar direto, ADR-0017).
// As rewrites são gravadas no build, então é no build que ela tem de existir.
const API_URL_INTERNA = obterApiUrlInterna();

function obterApiUrlInterna(): string {
  const valor = process.env.API_URL_INTERNA?.trim();
  if (valor) {
    return valor.replace(/\/+$/, "");
  }
  // Em produção, um default apontaria o proxy para um localhost que não existe, e o site
  // subiria "funcionando" sem backend. Melhor o build quebrar com a causa escrita.
  if (process.env.NODE_ENV === "production") {
    throw new Error(
      "Defina API_URL_INTERNA com a URL do backend (ex.: https://verifyscan.onrender.com). " +
        "Ela é lida no build; localmente, coloque-a em frontend/.env.local.",
    );
  }
  return "http://localhost:8000";
}

// O segredo que o `proxy.ts` manda ao backend junto com o IP do visitante (ADR-0024). Ele é lido
// em execução, mas a ausência é conferida aqui, no build: sem ele, o backend nunca confia no IP
// repassado, e todo visitante sem conta cai no IP do frontend — uma cota de IA só para todos, e
// 30 senhas erradas de qualquer um travariam o login de todos. Melhor o build quebrar.
if (process.env.NODE_ENV === "production" && !process.env.PROXY_SEGREDO?.trim()) {
  throw new Error(
    "Defina PROXY_SEGREDO com o mesmo valor do backend. Localmente, coloque-o em " +
      "frontend/.env.local (sem ele, fora de produção, o IP do visitante não é repassado).",
  );
}

const nextConfig: NextConfig = {
  // O Next regenera frontend/CLAUDE.md e frontend/AGENTS.md a cada `npm run dev`. Um CLAUDE.md
  // aninhado competiria com o arquivo de contexto do projeto, que é o da raiz do monorepo.
  agentRules: false,

  // /conta não tem conteúdo próprio: a seção de entrada é o histórico (ADR-0016). Redirecionar
  // aqui, e não com `redirect()` numa página, porque a página seria pré-renderizada estática e
  // deixaria o redirecionamento para o JavaScript do navegador — medido: aberta direto, ficava
  // em /conta. Pelo config é um 307 do servidor.
  async redirects() {
    return [{ source: "/conta", destination: "/conta/historico", permanent: false }];
  },

  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_URL_INTERNA}/api/:path*` },
      { source: "/health", destination: `${API_URL_INTERNA}/health` },
    ];
  },

  experimental: {
    // O backend gratuito leva até ~60 s para acordar; o default de 30 s cortaria o primeiro acesso.
    proxyTimeout: 90_000,
    // Com o `proxy.ts` (ADR-0024), o Next guarda o corpo do pedido em memória até este teto e,
    // acima dele, corta o corpo e só avisa no log. O default (10 MB) fica a ~0,4 MB do maior
    // corpo que o backend aceita: `imagem_max_bytes` no teto de 7,5 MB vira ~10,07 MB em base64
    // com a folga do JSON (`_limite_do_corpo`, em backend/app/api/analises.py). Hoje, com 5 MB,
    // o corpo chega a ~7,06 MB.
    proxyClientMaxBodySize: "11mb",
  },
};

// Sentry (ADR-0026). Sem NEXT_PUBLIC_SENTRY_DSN, a configuração sai como sempre saiu: o build não
// muda em nada. Com ela, o `withSentryConfig` acrescenta a reescrita do túnel (o navegador manda
// os eventos para `CAMINHO_DO_TUNEL`, no nosso domínio, e a rota `app/sentry-tunnel` os reenvia)
// e, só se houver SENTRY_AUTH_TOKEN, envia os source maps no build. Sem o token o build passa
// igual: os erros chegam ao Sentry com a pilha do código minificado.
const TEM_SENTRY = Boolean(process.env.NEXT_PUBLIC_SENTRY_DSN?.trim());
const TOKEN_DO_SENTRY = process.env.SENTRY_AUTH_TOKEN?.trim();

export default TEM_SENTRY
  ? withSentryConfig(nextConfig, {
      tunnelRoute: CAMINHO_DO_TUNEL,
      org: process.env.SENTRY_ORG,
      project: process.env.SENTRY_PROJECT,
      authToken: TOKEN_DO_SENTRY,
      sourcemaps: { disable: !TOKEN_DO_SENTRY },
      // Sem o aviso de "falta o token" a cada build, e sem telemetria do plugin para o Sentry.
      silent: true,
      telemetry: false,
    })
  : nextConfig;
