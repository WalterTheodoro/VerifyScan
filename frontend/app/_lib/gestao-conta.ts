// Trocar senha e excluir a conta (ADR-0019), pelo proxy do Next (ADR-0014). Envios: esperam o
// backend acordar e saem uma vez só (ADR-0017). Nada aqui mexe em React.
//
// Senha errada volta 400 com `detail`, e não 401: só o 401 vira "deslogado".

import { lerDetail, MENSAGEM_SEM_SERVIDOR } from "./conta";
import type { Resultado } from "./historico";
import { enviarUmaVez, type OpcoesDeEspera } from "./servidor";

// Para o 422 em formato de lista do FastAPI (corpo malformado), que não serve para exibir.
const MENSAGEM_CONFIRA = "Confira os dados e tente de novo.";

async function enviar(
  caminho: "/api/conta/senha" | "/api/conta/excluir",
  corpo: Record<string, string>,
  opcoes: OpcoesDeEspera,
): Promise<Resultado<true>> {
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
    return { situacao: "erro", mensagem: MENSAGEM_SEM_SERVIDOR };
  }
  if (resposta.status === 401) {
    return { situacao: "deslogado" };
  }
  if (resposta.status === 204) {
    return { situacao: "ok", dados: true };
  }
  const detalhe = lerDetail(resposta.corpo);
  if (typeof detalhe === "string") {
    return { situacao: "erro", mensagem: detalhe };
  }
  return {
    situacao: "erro",
    mensagem: resposta.status < 500 ? MENSAGEM_CONFIRA : MENSAGEM_SEM_SERVIDOR,
  };
}

/** 204: senha trocada, e as outras sessões da conta foram encerradas; esta continua. */
export function trocarSenha(
  senhaAtual: string,
  novaSenha: string,
  opcoes: OpcoesDeEspera,
): Promise<Resultado<true>> {
  return enviar("/api/conta/senha", { senha_atual: senhaAtual, nova_senha: novaSenha }, opcoes);
}

/** 204: conta, sessões e histórico apagados; o backend já limpou o cookie. */
export function excluirConta(senha: string, opcoes: OpcoesDeEspera): Promise<Resultado<true>> {
  return enviar("/api/conta/excluir", { senha }, opcoes);
}
