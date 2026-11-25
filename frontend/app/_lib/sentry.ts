// Rastreamento de erros do frontend com o Sentry (ADR-0026): o que é enviado e o que nunca é.
//
// O Sentry é um serviço de fora. Daqui não pode sair nada que a pessoa digitou nem nada que diga
// quem ela é: o texto da mensagem, o print, o e-mail, o cookie da sessão, o endereço IP. Por isso:
//
// - sem Session Replay, que grava a tela e o que é digitado (ele não está nas integrações padrão,
//   e nenhum arquivo o liga);
// - a coleta automática do SDK desligada, categoria por categoria (`COLETA`);
// - `limparEvento` em todo erro e em toda transação, antes do envio;
// - o navegador não fala com o Sentry: manda o evento para o nosso domínio (`CAMINHO_DO_TUNEL`),
//   e a rota `app/sentry-tunnel/route.ts` o reenvia sem os cabeçalhos de IP (`pedidoSemIp`).
//
// Tudo aqui é função pura; do SDK vem só o TIPO das opções, que some na compilação. Os testes
// rodam sem ele e sem rede.

import type { BrowserOptions, httpIntegration } from "@sentry/nextjs";

/** O que o SDK pode coletar sozinho, por categoria. TODAS estão escritas, de propósito: na versão
 *  11 do SDK a opção `sendDefaultPii` deixou de existir, e a categoria que fica de fora de
 *  `dataCollection` é COLETADA (o padrão é coletar tudo: usuário, cookies, corpos, query string).
 *  O `Required` faz o compilador reclamar se uma versão nova do SDK trouxer outra categoria, e há
 *  um teste que compara esta lista com a do SDK. */
export const COLETA = {
  // Sem isto o SDK pede ao Sentry para deduzir o IP de quem enviou o evento.
  userInfo: false,
  cookies: false,
  // Só o valor dos cabeçalhos desta lista.
  httpHeaders: {
    request: { allow: ["content-type", "user-agent", "x-request-id"] },
    response: false,
  },
  httpBodies: [],
  urlQueryParams: false,
  graphQL: { document: false, variables: false },
  genAI: { inputs: false, outputs: false },
  mcp: { inputs: false, outputs: false },
  databaseQueryData: false,
  queues: false,
  stackFrameVariables: false,
  // Linhas do NOSSO código em volta de cada quadro da pilha: é código, não dado de ninguém.
  frameContextLines: 5,
} satisfies Required<NonNullable<BrowserOptions["dataCollection"]>>;

/** Para onde o navegador manda os eventos. Fora de `/api`: o `proxy.ts` e as rewrites do backend
 *  não podem tocar neste caminho (o evento iria para o backend, com o segredo do proxy). Sem
 *  "sentry" no nome, que as listas de bloqueio de anúncio barram. */
export const CAMINHO_DO_TUNEL = "/monitoramento";

/** Fração das navegações que viram transação de desempenho. */
export const AMOSTRA_DE_DESEMPENHO = 0.1;

/** Cabeçalhos que nunca saem, em minúsculas. Os mesmos do backend (`app/core/sentry.py`). */
export const CABECALHOS_PROIBIDOS: readonly string[] = [
  "authorization",
  "cookie",
  "set-cookie",
  "x-forwarded-for",
  "x-real-ip",
  "forwarded",
  "x-verifyscan-ip",
  "x-verifyscan-segredo",
];

/** Do pedido do navegador, o que a função do túnel pode ver. Os cabeçalhos de IP ficam de fora:
 *  é a partir deles que o SDK monta o `X-Sentry-Forwarded-For`. */
const CABECALHOS_DO_TUNEL: readonly string[] = [
  "content-length",
  "content-type",
  "origin",
  "user-agent",
];

/** O formato do evento que interessa à limpeza. O tipo completo é do SDK; aqui só o que é lido. */
export type EventoDoSentry = {
  request?: {
    url?: string;
    method?: string;
    data?: unknown;
    cookies?: unknown;
    query_string?: unknown;
    env?: unknown;
    headers?: Record<string, string>;
  };
  user?: unknown;
  breadcrumbs?: unknown;
  message?: unknown;
  logentry?: unknown;
  exception?: {
    values?: {
      value?: string;
      stacktrace?: { frames?: { vars?: unknown }[] };
    }[];
  };
  // Só nas transações de desempenho.
  transaction?: string;
  transaction_info?: { source?: string };
  contexts?: { trace?: { data?: unknown } };
  spans?: { description?: string; data?: unknown }[];
};

/** O nome de uma transação sem rota conhecida. O mesmo do backend (`app/core/requisicao.py`). */
export const ROTA_NAO_MAPEADA = "nao_mapeada";

/** A URL sem a query string e sem o que vem depois do `#`. */
function semQuery(url: string): string {
  return url.split(/[?#]/, 1)[0];
}

/** Tira do evento tudo o que pode trazer dado de quem usa o site. Serve de `beforeSend` e de
 *  `beforeSendTransaction`. Nunca descarta o evento: devolve o mesmo, mais magro.
 *
 *  A mensagem da exceção sai sempre, como no backend: é nela que o conteúdo vaza (um erro de
 *  JSON cita o começo do texto que não conseguiu ler). Ficam o tipo e a pilha. */
export function limparEvento<Evento extends EventoDoSentry>(evento: Evento): Evento {
  const pedido = evento.request;
  if (pedido) {
    const limpo: EventoDoSentry["request"] = {};
    if (pedido.method) {
      limpo.method = pedido.method;
    }
    if (pedido.url) {
      limpo.url = semQuery(pedido.url);
    }
    if (pedido.headers) {
      limpo.headers = Object.fromEntries(
        Object.entries(pedido.headers).filter(
          ([nome]) => !CABECALHOS_PROIBIDOS.includes(nome.toLowerCase()),
        ),
      );
    }
    evento.request = limpo;
  }
  delete evento.user;
  delete evento.breadcrumbs;
  delete evento.message;
  delete evento.logentry;
  for (const excecao of evento.exception?.values ?? []) {
    delete excecao.value;
    for (const quadro of excecao.stacktrace?.frames ?? []) {
      delete quadro.vars;
    }
  }
  // Das transações ficam o nome da rota, a duração e o status de cada trecho. Os atributos
  // (`data`) saem todos: é neles que o SDK anota endereço, query string e cabeçalhos.
  if (evento.transaction && evento.transaction_info?.source !== "route") {
    // Sem rota conhecida, o nome da transação é o caminho cru, com o que alguém digitou.
    evento.transaction = ROTA_NAO_MAPEADA;
  }
  if (evento.contexts?.trace) {
    delete evento.contexts.trace.data;
  }
  for (const trecho of evento.spans ?? []) {
    delete trecho.data;
    if (trecho.description) {
      trecho.description = semQuery(trecho.description);
    }
  }
  return evento;
}

/** As opções comuns do `Sentry.init` (navegador e servidor do Next), ou `null` sem DSN: sem a
 *  variável, o SDK nem é inicializado. */
export function opcoesDoSentry(dsn: string | undefined, ambiente?: string) {
  const valor = dsn?.trim();
  if (!valor) {
    return null;
  }
  return {
    dsn: valor,
    environment: ambiente?.trim() || undefined,
    dataCollection: COLETA,
    tracesSampleRate: AMOSTRA_DE_DESEMPENHO,
    // Na versão 11 do SDK o padrão é "stream": os trechos saem em lotes, e o
    // `beforeSendTransaction` é IGNORADO (o próprio SDK avisa no terminal). Com "static", a
    // transação sai inteira, no fim, e passa pelo `limparEvento`.
    traceLifecycle: "static" as const,
    // Sem rastro de cliques, de console e de chamadas: o `limparEvento` também os remove.
    maxBreadcrumbs: 0,
    beforeSend: limparEvento,
    beforeSendTransaction: limparEvento,
    // `satisfies`: o compilador recusa aqui uma opção que o SDK não conhece. Sem isto, o
    // `sendDefaultPii`, que não existe mais, ficou sem efeito e sem aviso nenhum.
  } satisfies BrowserOptions;
}

/** Integrações padrão do SDK que ficam desligadas no navegador, pelo nome que o SDK dá a elas.
 *  - "BrowserSession" manda um envio a cada página aberta, mesmo sem erro, para contar sessões
 *    (Release Health). Não usamos a contagem, e o aviso de privacidade fala de erros e desempenho.
 *  - "CultureContext" anexa o idioma, o fuso e o calendário do navegador a cada envio.
 *  Na versão 11 do SDK não há opção para nenhuma das duas: o jeito é tirá-las da lista. */
export const INTEGRACOES_DESLIGADAS: readonly string[] = ["BrowserSession", "CultureContext"];

/** As opções do `Sentry.init` no navegador: as comuns, mais a lista de integrações sem as
 *  desligadas. O SDK chama a função com as integrações padrão e usa o que ela devolver. */
export function opcoesDoNavegador(dsn: string | undefined, ambiente?: string) {
  const comuns = opcoesDoSentry(dsn, ambiente);
  if (!comuns) {
    return null;
  }
  return {
    ...comuns,
    integrations: <Integracao extends { name: string }>(padrao: Integracao[]) =>
      padrao.filter((integracao) => !INTEGRACOES_DESLIGADAS.includes(integracao.name)),
  } satisfies BrowserOptions;
}

/** No servidor do Next (runtime Node), a integração padrão "ProcessSession" abre uma sessão por
 *  processo e a manda ao Sentry na primeira requisição. O runtime edge não tem nenhuma das duas
 *  coisas. */
export const INTEGRACOES_DESLIGADAS_NO_SERVIDOR: readonly string[] = ["ProcessSession"];

/** A integração de HTTP do servidor do Next. `maxRequestBodySize`: o corpo dos pedidos a /api/* é
 *  a mensagem ou o print da pessoa, e por padrão o SDK guarda um pedaço dele para anexar a um
 *  erro. `sessions`: por padrão, cada requisição entra numa contagem agregada de sessões, enviada
 *  mesmo sem erro. */
export const OPCOES_DO_HTTP_NO_SERVIDOR = {
  maxRequestBodySize: "none",
  sessions: false,
} as const satisfies NonNullable<Parameters<typeof httpIntegration>[0]>;

/** As integrações do servidor do Next: as padrão, sem as desligadas e com a `Http` trocada pela
 *  nossa (`http`, feita com `OPCOES_DO_HTTP_NO_SERVIDOR`). */
export function integracoesDoServidor<Integracao extends { name: string }>(
  padrao: Integracao[],
  http: Integracao,
): Integracao[] {
  return padrao
    .filter(
      (integracao) =>
        integracao.name !== "Http" && !INTEGRACOES_DESLIGADAS_NO_SERVIDOR.includes(integracao.name),
    )
    .concat(http);
}

/** O pedido do navegador sem os cabeçalhos de IP, para entregar à função do túnel do SDK. Ela
 *  repassa ao Sentry o IP que achar em `x-forwarded-for` (e parecidos); sem eles, o Sentry só vê
 *  o endereço do nosso servidor. O corpo segue como veio, sem ser lido aqui. */
export function pedidoSemIp(pedido: Request): Request {
  const cabecalhos = new Headers();
  for (const nome of CABECALHOS_DO_TUNEL) {
    const valor = pedido.headers.get(nome);
    if (valor) {
      cabecalhos.set(nome, valor);
    }
  }
  return new Request(pedido.url, {
    method: "POST",
    headers: cabecalhos,
    body: pedido.body,
    // O Node exige isto para um corpo em fluxo. Não está no tipo do DOM.
    duplex: "half",
  } as RequestInit);
}
