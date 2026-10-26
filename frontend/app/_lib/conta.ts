// Chamadas de conta ao backend (ADR-0013), sempre por caminho relativo: o Next repassa /api/* ao
// backend, e o cookie de sessão fica no domínio do próprio site (ADR-0014). Nada aqui mexe em
// React: só busca e traduz a resposta em algo que a tela mostra. A espera pelo backend que dorme
// e a classificação de quem respondeu ficam em `servidor.ts` (ADR-0017).
//
// A pasta `_lib` começa com "_" para o App Router não tratá-la como rota.

import { enviarUmaVez, lerSessao, type OpcoesDeEspera } from "./servidor";

export type Usuario = { nome: string; email: string };

export type ResultadoConta = { ok: true; usuario: Usuario } | { ok: false; mensagem: string };

export const MENSAGEM_SEM_SERVIDOR =
  "Não conseguimos falar com o servidor. Tente de novo em instantes.";

// Para o 422 em formato de lista do FastAPI (corpo malformado), que não serve para exibir.
const MENSAGEM_CONFIRA = "Confira os dados e tente de novo.";

/** O `detail` do corpo de erro do backend, se houver. */
export function lerDetail(corpo: unknown): unknown {
  return corpo && typeof corpo === "object" && "detail" in corpo ? corpo.detail : undefined;
}

function ehUsuario(corpo: unknown): corpo is Usuario {
  return (
    !!corpo &&
    typeof corpo === "object" &&
    "nome" in corpo &&
    typeof corpo.nome === "string" &&
    "email" in corpo &&
    typeof corpo.email === "string"
  );
}

/** Cadastro ou login. A frase de erro do backend já é a mensagem ao usuário (ADR-0013 §5).
 *  Sai uma vez só: repetir o cadastro daria 409 a quem acabou de se cadastrar. */
export async function enviarConta(
  caminho: "/api/auth/cadastro" | "/api/auth/login",
  corpo: Record<string, string>,
  opcoes: OpcoesDeEspera = {},
): Promise<ResultadoConta> {
  const resposta = await enviarUmaVez(
    caminho,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo),
    },
    opcoes,
  );
  if (!resposta.doBackend) {
    return { ok: false, mensagem: MENSAGEM_SEM_SERVIDOR };
  }
  if (resposta.status >= 200 && resposta.status < 300 && ehUsuario(resposta.corpo)) {
    return { ok: true, usuario: resposta.corpo };
  }
  const detalhe = lerDetail(resposta.corpo);
  if (typeof detalhe === "string") {
    return { ok: false, mensagem: detalhe };
  }
  if (Array.isArray(detalhe) || (resposta.status >= 400 && resposta.status < 500)) {
    return { ok: false, mensagem: MENSAGEM_CONFIRA };
  }
  return { ok: false, mensagem: MENSAGEM_SEM_SERVIDOR };
}

export type Sessao =
  | { situacao: "logado"; usuario: Usuario }
  | { situacao: "deslogado" }
  | { situacao: "erro" };

/** Quem está logado. Repete sozinho enquanto o backend acorda; só o 401 é "deslogado". "erro" é
 *  "não deu para saber": o cabeçalho mostra "Entrar", a área da conta mostra o aviso. */
export async function consultarSessao(opcoes: OpcoesDeEspera = {}): Promise<Sessao> {
  const sessao = await lerSessao(opcoes);
  if (sessao.situacao === "logado") {
    return ehUsuario(sessao.corpo)
      ? { situacao: "logado", usuario: sessao.corpo }
      : { situacao: "erro" };
  }
  return sessao.situacao === "deslogado" ? { situacao: "deslogado" } : { situacao: "erro" };
}

/** Sai da conta. Devolve `true` só quando a resposta comprovadamente veio do backend — que
 *  limpa o cookie no 204 e também no 503 (com `detail`). Sem resposta do backend o cookie
 *  continua válido, e dizer "saiu" seria mentir (ADR-0014). */
export async function sairDaConta(): Promise<boolean> {
  const resposta = await enviarUmaVez("/api/auth/logout", { method: "POST" });
  if (!resposta.doBackend) {
    return false;
  }
  return resposta.status === 204 || lerDetail(resposta.corpo) !== undefined;
}
