import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // O Next regenera frontend/CLAUDE.md e frontend/AGENTS.md a cada `npm run dev`. Um CLAUDE.md
  // aninhado competiria com o arquivo de contexto do projeto, que é o da raiz do monorepo.
  agentRules: false,
};

export default nextConfig;
