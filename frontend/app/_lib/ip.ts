// O IP do visitante, repassado ao backend pelo proxy do Next (fatia 10, ADR-0024).
//
// O backend só vê o IP do frontend, porque o Next repassa /api/* (ADR-0014): um limite por esse IP
// juntaria todo mundo numa cota só. Por isso o `proxy.ts` manda o IP do visitante num cabeçalho
// próprio, junto com o segredo compartilhado; o backend só confia nele quando o segredo confere.
//
// Qual IP: a entrada mais à direita do `X-Forwarded-For`. O Render não documenta o cabeçalho; o
// único registro dele (o quadro de sugestões) diz que ele acrescenta ao que o navegador mandou,
// sem limpar. A da esquerda pode ser forjada; a última, quem pôs foi o Render. É a mesma regra do
// backend (`app/core/ip.py`).
//
// Sem imports de valor, para o teste rodar no Node direto (type stripping).

export const CABECALHO_IP = "x-verifyscan-ip";
export const CABECALHO_SEGREDO = "x-verifyscan-segredo";

const IPV4 = /^\d{1,3}(\.\d{1,3}){3}$/;

/** Validação simples: quem normaliza (IPv6 por /64) é o backend. */
function pareceIp(texto: string): boolean {
  if (IPV4.test(texto)) {
    return texto.split(".").every((parte) => Number(parte) <= 255);
  }
  if (!texto.includes(":")) {
    return false;
  }
  // O parser de URL valida IPv6 entre colchetes; um texto qualquer com ":" não passa.
  try {
    new URL(`http://[${texto}]`);
    return true;
  } catch {
    return false;
  }
}

/** A última entrada do `X-Forwarded-For`, se for um IP. `Headers.get` junta cabeçalhos repetidos
 *  com vírgula, na ordem: a última entrada continua sendo a do Render. */
export function ipDoVisitante(encaminhado: string | null): string | null {
  const ultimo = (encaminhado ?? "").split(",").at(-1)?.trim() ?? "";
  return pareceIp(ultimo) ? ultimo : null;
}

/** Os cabeçalhos que seguem para o backend. Os dois do proxy sempre saem do que o navegador
 *  mandou, e só voltam com o segredo e um IP válido. Devolve uma cópia. */
export function cabecalhosParaOBackend(recebidos: Headers, segredo: string | undefined): Headers {
  const enviados = new Headers(recebidos);
  enviados.delete(CABECALHO_IP);
  enviados.delete(CABECALHO_SEGREDO);
  const ip = ipDoVisitante(recebidos.get("x-forwarded-for"));
  if (segredo && ip) {
    enviados.set(CABECALHO_IP, ip);
    enviados.set(CABECALHO_SEGREDO, segredo);
  }
  return enviados;
}
