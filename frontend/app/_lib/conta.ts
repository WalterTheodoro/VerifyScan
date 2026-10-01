// Chamadas de conta ao backend (ADR-0013), sempre por caminho relativo: o Next repassa /api/* ao
// backend, e o cookie de sessão fica no domínio do próprio site (ADR-0014). Nada aqui mexe em
// React: só busca e traduz a resposta em algo que a tela mostra.
//
// A pasta `_lib` começa com "_" para o App Router não tratá-la como rota.

export type Usuario = { nome: string; email: string };

export type ResultadoConta = { ok: true; usuario: Usuario } | { ok: false; mensagem: string };

export const MENSAGEM_SEM_SERVIDOR =
  "Não conseguimos falar com o servidor. Tente de novo em instantes.";

// Para o 422 em formato de lista do FastAPI (corpo malformado), que não serve para exibir.
const MENSAGEM_CONFIRA = "Confira os dados e tente de novo.";

/** O `detail` do corpo de erro do backend, se houver. */
function lerDetail(corpo: unknown): unknown {
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

/** Cadastro ou login. A frase de erro do backend já é a mensagem ao usuário (ADR-0013 §5). */
export async function enviarConta(
  caminho: "/api/auth/cadastro" | "/api/auth/login",
  corpo: Record<string, string>,
): Promise<ResultadoConta> {
  try {
    const resposta = await fetch(caminho, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo),
    });
    // Corpo que não é JSON é o Next respondendo no lugar do backend (proxy sem resposta).
    const dados: unknown = await resposta.json().catch(() => null);

    if (resposta.ok && ehUsuario(dados)) {
      return { ok: true, usuario: dados };
    }
    const detalhe = lerDetail(dados);
    if (typeof detalhe === "string") {
      return { ok: false, mensagem: detalhe };
    }
    if (Array.isArray(detalhe) || (resposta.status >= 400 && resposta.status < 500)) {
      return { ok: false, mensagem: MENSAGEM_CONFIRA };
    }
    return { ok: false, mensagem: MENSAGEM_SEM_SERVIDOR };
  } catch {
    return { ok: false, mensagem: MENSAGEM_SEM_SERVIDOR };
  }
}

/** Quem está logado. `null` cobre o 401 ("deslogado", não erro) e também qualquer falha: sem
 *  como saber, o cabeçalho oferece "Entrar", que é inofensivo. */
export async function consultarSessao(): Promise<Usuario | null> {
  try {
    const resposta = await fetch("/api/auth/eu", { cache: "no-store" });
    const dados: unknown = await resposta.json().catch(() => null);
    return resposta.ok && ehUsuario(dados) ? dados : null;
  } catch {
    return null;
  }
}

/** Sai da conta. Devolve `true` só quando a resposta comprovadamente veio do backend — que
 *  limpa o cookie no 204 e também no 503 (com `detail`). Falha de rede ou 5xx sem JSON é o
 *  proxy sem backend: o cookie continua válido, e dizer "saiu" seria mentir (ADR-0014). */
export async function sairDaConta(): Promise<boolean> {
  try {
    const resposta = await fetch("/api/auth/logout", { method: "POST" });
    if (resposta.status === 204) {
      return true;
    }
    const dados: unknown = await resposta.json().catch(() => null);
    return lerDetail(dados) !== undefined;
  } catch {
    return false;
  }
}
