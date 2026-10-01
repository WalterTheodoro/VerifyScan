import type { NextConfig } from "next";

// O navegador fala só com o frontend, e o Next repassa /api/* e /health ao backend (ADR-0014).
// Assim o cookie de sessão fica first-party no domínio do frontend: onrender.com está na Public
// Suffix List, e um cookie do backend seria de terceiro — o Safari bloqueia (ADR-0013).
//
// Variável de servidor, sem NEXT_PUBLIC_: o navegador nunca precisa saber onde o backend mora.
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

const nextConfig: NextConfig = {
  // O Next regenera frontend/CLAUDE.md e frontend/AGENTS.md a cada `npm run dev`. Um CLAUDE.md
  // aninhado competiria com o arquivo de contexto do projeto, que é o da raiz do monorepo.
  agentRules: false,

  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_URL_INTERNA}/api/:path*` },
      { source: "/health", destination: `${API_URL_INTERNA}/health` },
    ];
  },

  experimental: {
    // O backend gratuito leva até ~60 s para acordar; o default de 30 s cortaria o primeiro acesso.
    proxyTimeout: 90_000,
  },
};

export default nextConfig;
