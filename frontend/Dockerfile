# syntax=docker/dockerfile:1
#
# Imagem do frontend (ADR-0029). Gerada no GitHub Actions e publicada no GHCR com o SHA do commit.
# A imagem é pública. O que entra nela no build são só valores públicos: as NEXT_PUBLIC_*, que o
# Next grava no JavaScript do navegador de qualquer jeito, e o endereço interno do backend. O
# PROXY_SEGREDO verdadeiro chega em execução, pelo ambiente do contêiner.
#
#   docker build -t verifyscan-frontend frontend

# ── 1. dependências ──────────────────────────────────────────────────────────────────────────
FROM node:22-slim AS dependencias

WORKDIR /app

# Só os dois arquivos de dependência primeiro: mudar código não refaz esta camada.
# Sem os scripts de instalação dos pacotes, como no CI.
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

# ── 2. build ─────────────────────────────────────────────────────────────────────────────────
FROM node:22-slim AS build

WORKDIR /app

COPY --from=dependencias /app/node_modules ./node_modules
COPY . .

# Para onde o Next repassa /api/* e /health (ADR-0014): o nome do serviço no compose. É gravado
# nas rewrites, no build. Não é segredo e não é alcançável de fora da rede do compose.
ARG API_URL_INTERNA=http://backend:8000

# Públicas por definição: vão para o JavaScript do navegador. No CI, vêm das variáveis do GitHub.
ARG NEXT_PUBLIC_CONTATO_PRIVACIDADE=
ARG NEXT_PUBLIC_SENTRY_DSN=
ARG NEXT_PUBLIC_SENTRY_ENVIRONMENT=
# Só nomes, para o envio dos source maps. O NEXT_PUBLIC_URL_DESPERTAR fica de fora de propósito:
# na VM o backend não dorme nem é público (ADR-0029).
ARG SENTRY_ORG=
ARG SENTRY_PROJECT=

# SAIDA_STANDALONE liga o `output: "standalone"` do next.config.ts, só aqui.
# NEXT_PUBLIC_HOSPEDAGEM faz o aviso de privacidade dizer onde ESTA imagem roda: na VM da Azure,
# no Chile. Fixa aqui, e não uma variável do CI: a imagem só existe para a VM.
ENV NEXT_TELEMETRY_DISABLED=1 \
    SAIDA_STANDALONE=1 \
    NEXT_PUBLIC_HOSPEDAGEM=azure

# Dois cuidados nesta linha:
# - o token do Sentry, se houver, entra como segredo de build: existe só durante este comando e
#   não fica em camada nem no histórico da imagem. Sem ele, o build passa igual (ADR-0026);
# - o next.config.ts recusa o build de produção sem PROXY_SEGREDO. O valor abaixo é público e só
#   satisfaz essa conferência: o `proxy.ts` lê o verdadeiro em execução.
RUN --mount=type=secret,id=sentry_auth_token,env=SENTRY_AUTH_TOKEN \
    PROXY_SEGREDO=valor-publico-so-do-build-nao-e-o-segredo \
    npm run build

# ── 3. execução ──────────────────────────────────────────────────────────────────────────────
FROM node:22-slim

WORKDIR /app

# HOSTNAME: o Docker define essa variável com o id do contêiner, e o servidor do Next escutaria
# só nesse nome. 0.0.0.0 escuta na rede do compose.
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

# A saída standalone traz o servidor e só os pacotes que ele usa. Os arquivos estáticos e a pasta
# public não vêm nela: são copiados para dentro, de onde o `server.js` os serve.
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public

# Usuário sem privilégio, que já vem na imagem do Node.
USER node
EXPOSE 3000

CMD ["node", "server.js"]
