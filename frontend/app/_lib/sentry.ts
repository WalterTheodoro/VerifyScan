// Rastreamento de erros do frontend com o Sentry (ADR-0026): o que é enviado e o que nunca é.
//
// O Sentry é um serviço de fora. Daqui não pode sair nada que a pessoa digitou nem nada que diga
// quem ela é: o texto da mensagem, o print, o e-mail, o cookie da sessão, o endereço IP. Por isso:
//
// - sem Session Replay, que grava a tela e o que é digitado (ele não está nas integrações padrão,
//   e nenhum arquivo o liga);
// - `sendDefaultPii: false`;
// - `limparEvento` em todo erro e em toda transação, antes do envio;
// - o navegador não fala com o Sentry: manda o evento para o nosso domínio (`CAMINHO_DO_TUNEL`),
//   e a rota `app/sentry-tunnel/route.ts` o reenvia sem os cabeçalhos de IP (`pedidoSemIp`).
//
// Tudo aqui é função pura, sem importar o SDK: os testes rodam sem ele e sem rede.

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
    sendDefaultPii: false,
    tracesSampleRate: AMOSTRA_DE_DESEMPENHO,
    // Na versão 11 do SDK o padrão é "stream": os trechos saem em lotes, e o
    // `beforeSendTransaction` é IGNORADO (o próprio SDK avisa no terminal). Com "static", a
    // transação sai inteira, no fim, e passa pelo `limparEvento`.
    traceLifecycle: "static" as const,
    // Sem rastro de cliques, de console e de chamadas: o `limparEvento` também os remove.
    maxBreadcrumbs: 0,
    beforeSend: limparEvento,
    beforeSendTransaction: limparEvento,
  };
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
