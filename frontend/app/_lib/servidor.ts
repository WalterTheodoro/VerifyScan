// Espera pelo backend (ADR-0017). No plano gratuito do Render o backend dorme e leva até ~60 s
// para acordar; enquanto isso, o proxy do Next (ADR-0014) devolve uma página de erro, não o JSON
// do backend. Aqui fica a única classificação de "quem respondeu" e as duas regras:
// leituras repetem sozinhas; envios esperam o backend e saem uma vez só.
//
// O pedido pelo proxy recebe 502 do Render sem acordar o backend; quem acorda é um GET do
// navegador ao endereço público (`despertar`, adendo do ADR-0017).
//
// Este arquivo não importa nada: o teste roda no Node direto (type stripping), que não lê o
// tsconfig nem resolve import sem extensão. Por isso também usa `setTimeout` e `Date.now()`
// globais, e não os de `window` — são os que o relógio falso do teste controla.

/** Do backend: veio corpo JSON (qualquer status) ou 204. De outra coisa: falha de rede, ou
 *  status sem corpo JSON — a página de erro do proxy ou do Render. */
export type Resposta = { doBackend: true; status: number; corpo: unknown } | { doBackend: false };

export type OpcoesDeEspera = {
  /** Chamado quando a espera começa, para a tela mostrar "O servidor está acordando". */
  aoEsperar?: () => void;
  /** Abortado quando a tela sai: para de tentar. */
  signal?: AbortSignal;
};

/** Intervalos entre as tentativas de uma leitura; o último se repete. */
export const INTERVALOS_MS = [2000, 3000, 5000];

/** Depois disto sem resposta, desiste: o Render leva até ~60 s para acordar, com folga. */
export const LIMITE_ESPERA_MS = 90_000;

/** Resposta do backend mais nova que isto dispensa a espera antes de um envio. O Render dorme
 *  15 min depois da última requisição, mesmo com a aba aberta; 10 min deixa margem. */
export const JANELA_ACORDADO_MS = 10 * 60_000;

/** Dois despertares nunca saem com menos que isto entre eles: sem rajada. */
export const INTERVALO_DESPERTAR_MS = 10_000;

const FORA_DO_BACKEND: Resposta = { doBackend: false };

let ultimaRespostaDoBackend: number | null = null;
let aquecimento: Promise<Resposta> | null = null;
let ultimoDespertar: number | null = null;

/** Endereço público do backend, ou "" sem a variável. Escrito por extenso porque o Next só
 *  embute no build a forma literal `process.env.NEXT_PUBLIC_...`; lido a cada chamada para o
 *  teste poder trocar. */
function urlDespertar(): string {
  return (process.env.NEXT_PUBLIC_URL_DESPERTAR ?? "").trim().replace(/\/+$/, "");
}

/** GET direto ao /health do endereço público, só para o Render acordar o backend. Sem cookie,
 *  sem ler a resposta (por isso não esbarra no ADR-0014); nunca lança, nunca é aguardado. Sem a
 *  variável (local), não faz nada: lá o proxy alcança o backend sem passar pelo Render. */
export function despertar(): void {
  const url = urlDespertar();
  if (!url) {
    return;
  }
  if (ultimoDespertar !== null && Date.now() - ultimoDespertar < INTERVALO_DESPERTAR_MS) {
    return;
  }
  ultimoDespertar = Date.now();
  try {
    void fetch(`${url}/health`, { mode: "no-cors", credentials: "omit", cache: "no-store" }).catch(
      () => {},
    );
  } catch {
    // fetch que lança na hora (bloqueado pelo navegador): o despertar é só uma tentativa.
  }
}

/** Um pedido, sem repetição, já classificado. */
export async function pedir(caminho: string, init: RequestInit = {}): Promise<Resposta> {
  let resposta: Response;
  try {
    resposta = await fetch(caminho, init);
  } catch {
    return FORA_DO_BACKEND;
  }
  // 204 não tem corpo, e só o backend o devolve (logout, apagar). A regra do "Sair" depende dele.
  let corpo: unknown = null;
  if (resposta.status !== 204) {
    try {
      corpo = await resposta.json();
    } catch {
      return FORA_DO_BACKEND;
    }
  }
  ultimaRespostaDoBackend = Date.now();
  return { doBackend: true, status: resposta.status, corpo };
}

function dormir(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolver) => {
    const timer = setTimeout(resolver, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        resolver();
      },
      { once: true },
    );
  });
}

const foraDoBackend = (resposta: Resposta) => !resposta.doBackend;

/** GET que tenta de novo sozinho enquanto `repetirSe` (padrão: a resposta não veio do backend),
 *  com intervalo crescente, até `LIMITE_ESPERA_MS`. Devolve a última resposta. */
export async function lerComRepeticao(
  caminho: string,
  {
    repetirSe = foraDoBackend,
    aoEsperar,
    signal,
  }: OpcoesDeEspera & { repetirSe?: (resposta: Resposta) => boolean } = {},
): Promise<Resposta> {
  const inicio = Date.now();
  let resposta = await pedir(caminho, { cache: "no-store", signal });
  for (let tentativa = 0; repetirSe(resposta) && !signal?.aborted; tentativa++) {
    const intervalo = INTERVALOS_MS[Math.min(tentativa, INTERVALOS_MS.length - 1)];
    if (Date.now() - inicio + intervalo > LIMITE_ESPERA_MS) {
      break;
    }
    if (tentativa === 0) {
      aoEsperar?.();
    }
    // A cada repetição, não só na primeira: um despertar perdido não pode deixar a espera inteira
    // sem nenhum. O intervalo mínimo segura a rajada.
    despertar();
    await dormir(intervalo, signal);
    if (signal?.aborted) {
      break;
    }
    resposta = await pedir(caminho, { cache: "no-store", signal });
  }
  return resposta;
}

export type SituacaoDaSessao =
  | { situacao: "logado"; corpo: unknown }
  | { situacao: "deslogado" }
  | { situacao: "indisponivel" };

/** GET /api/auth/eu. Só o 401 é "deslogado". O 503 com detail é o banco acordando (ADR-0013 §6)
 *  e entra na repetição, como a resposta que não veio do backend. */
export async function lerSessao(opcoes: OpcoesDeEspera = {}): Promise<SituacaoDaSessao> {
  const resposta = await lerComRepeticao("/api/auth/eu", {
    ...opcoes,
    repetirSe: (r) => !r.doBackend || r.status === 503,
  });
  if (!resposta.doBackend) {
    return { situacao: "indisponivel" };
  }
  if (resposta.status === 401) {
    return { situacao: "deslogado" };
  }
  if (resposta.status >= 200 && resposta.status < 300) {
    return { situacao: "logado", corpo: resposta.corpo };
  }
  return { situacao: "indisponivel" };
}

/** Um GET silencioso a /health, uma vez por carregamento: o backend começa a acordar enquanto a
 *  pessoa lê. A flag também segura o efeito duplo do StrictMode. */
export function aquecer(): void {
  if (aquecimento === null) {
    despertar();
    aquecimento = pedir("/health", { cache: "no-store" });
  }
}

const acordadoHaPouco = () =>
  ultimaRespostaDoBackend !== null && Date.now() - ultimaRespostaDoBackend < JANELA_ACORDADO_MS;

/** Resolve quando o backend responde (true) ou quando desiste (false). Com resposta recente, na
 *  hora; senão aproveita o aquecimento e, se ainda preciso, consulta /health com repetição. */
export async function esperarPeloBackend(opcoes: OpcoesDeEspera = {}): Promise<boolean> {
  if (acordadoHaPouco()) {
    return true;
  }
  despertar();
  if (aquecimento !== null) {
    await aquecimento;
    if (acordadoHaPouco()) {
      return true;
    }
  }
  return (await lerComRepeticao("/health", opcoes)).doBackend;
}

/** POST/DELETE. Nunca repete: o backend pode ter processado o pedido sem a resposta chegar, e
 *  repetir daria 409 no cadastro ou gravaria a análise duas vezes. Espera o backend antes; se ele
 *  não apareceu, não envia. */
export async function enviarUmaVez(
  caminho: string,
  init: RequestInit,
  opcoes: OpcoesDeEspera = {},
): Promise<Resposta> {
  if (!(await esperarPeloBackend(opcoes))) {
    return FORA_DO_BACKEND;
  }
  return pedir(caminho, { ...init, signal: opcoes.signal });
}

/** Só para os testes: zera o estado de módulo entre um caso e outro. */
export function esquecerBackend(): void {
  ultimaRespostaDoBackend = null;
  aquecimento = null;
  ultimoDespertar = null;
}
