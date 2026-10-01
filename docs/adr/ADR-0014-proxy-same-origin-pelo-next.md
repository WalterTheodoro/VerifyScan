# ADR-0014 — Proxy same-origin pelo Next

**Data:** 2026-10-01 · **Status:** aceito · **Fase:** 8 (fatia 3)

## Contexto

O ADR-0013 grava o cookie de sessão `vs_sessao` sem `Domain`. O problema é que `onrender.com`
está na Public Suffix List. Por isso `verifyscan-app.onrender.com` (frontend) e
`verifyscan.onrender.com` (backend) são *sites* diferentes. Se o navegador chamasse o backend
direto, o cookie seria de terceiro, e o Safari o bloqueia. O bloqueio vale também para o Chrome no
iPhone, que usa o mesmo motor.

Em `localhost` o problema não aparece, porque a porta não muda o site. Por isso o aceite local é em
build de produção pela porta 3000, e o critério final é no iPhone.

## Opções consideradas

- **Proxy pelo Next.** O navegador chama só caminhos relativos, e o Next repassa `/api/*` e
  `/health` ao backend.
- **Domínio próprio**, com frontend e backend em subdomínios do mesmo domínio registrado. Custa
  dinheiro e DNS, e não existe hoje.
- **Token no `localStorage`**, enviado em `Authorization`. Fica legível por qualquer script da
  página (XSS), contradiz o `HttpOnly` do ADR-0013 e refaz a autenticação.

## Decisão

**Proxy pelo Next, com `rewrites` em `frontend/next.config.ts`.**

- As rotas: `/api/:path*` → `${API_URL_INTERNA}/api/:path*` e `/health` → `${API_URL_INTERNA}/health`.
- `API_URL_INTERNA` é variável de servidor, sem `NEXT_PUBLIC_`, e é lida no build, porque as
  rewrites ficam gravadas no `routes-manifest.json`.
  - Fora de produção, o default é `http://localhost:8000`.
  - Um build de produção sem a variável **falha com mensagem clara**, em vez de subir apontando para
    um localhost que não existe.
- `NEXT_PUBLIC_API_URL` sai do código. Todo `fetch` do navegador é relativo.
- **Sair só mostra "deslogado" quando a resposta comprovadamente veio do backend**: 204, ou erro com
  `detail`. O público divide celular e computador com a família, e mostrar "Entrar" com o cookie
  ainda válido deixaria a conta aberta para quem viesse depois.

**Conferido no código instalado (Next 16.3.3, `node_modules/next/dist`):**

- **O Host é reescrito.**
  - `server/lib/router-utils/proxy-request.js:33` cria o proxy (httpxy) com `changeOrigin: true`.
  - Em `compiled/httpxy/index.js`, essa opção põe em `Host` o host do destino.
  - É isso que importa no Render, que escolhe o serviço pelo `Host`. Se o proxy mandasse
    `verifyscan-app.onrender.com`, a requisição voltaria para o frontend, e o teste em localhost
    não pegaria isso.
  - O host original segue em `x-forwarded-host` (linha 39).
- **O cookie passa intacto.** O httpxy só reescreve `Set-Cookie` com `cookieDomainRewrite`, e o Next
  não passa essa opção.
- **Timeout.**
  - `experimental.proxyTimeout` existe: `server/config-schema.js:315`.
  - O default é `undefined` (`server/config-shared.js:229`), que vira **30 000 ms** em
    `proxy-request.js:37`.
  - Configurado em **90 000 ms**: o backend gratuito leva até ~60 s para acordar.

## Custo de estar errado

- **Um salto a mais por requisição** (navegador → Next → backend). No volume do projeto não pesa
  diante do OCR e das APIs externas do ADR-0002.
- **Os dois serviços precisam estar acordados.** No plano gratuito, a primeira requisição pode
  esperar o despertar dos dois. A tela avisa depois de 5 s ("O servidor está acordando…").
- **O CORS do backend deixa de ser usado pelo navegador.** Ele continua configurado, mas o
  navegador não faz mais chamada cross-origin. Quem ler o código pode achar que o CORS ainda
  sustenta alguma coisa.
- **A troca para domínio próprio é barata:** muda o valor de `API_URL_INTERNA` (ou volta a chamada
  direta) e cria um registro DNS. O cookie sem `Domain` continua certo nos dois desenhos.
