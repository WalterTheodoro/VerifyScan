// Chamadas da área "Minha conta" ao backend (ADR-0015): histórico e dados da conta. Caminho
// relativo, pelo proxy do Next (ADR-0014). Nada aqui mexe em React.

import type { NivelRisco } from "../_componentes/nivel-risco";
import { lerDetail, MENSAGEM_SEM_SERVIDOR } from "./conta";

export type FatorDoHistorico = { categoria: string; descricao: string; peso: number };

export type AnaliseDoHistorico = {
  id: string;
  created_at: string;
  nivel_risco: NivelRisco;
  score_risco: number;
  fatores: FatorDoHistorico[];
};

export type Historico = { dias: number; analises: AnaliseDoHistorico[] };

export type DadosConta = { nome: string; email: string; criado_em: string };

/** Espelho do default de `HISTORICO_DIAS` no backend (ADR-0015), para telas que não carregam o
 *  histórico. A lista usa o `dias` que a API devolve; se a variável mudar no Render, este número
 *  precisa mudar junto. */
export const HISTORICO_DIAS = 7;

/** Três desfechos que a tela trata de jeitos diferentes: mostrar, pedir login, ou avisar. */
export type Resultado<T> =
  | { situacao: "ok"; dados: T }
  | { situacao: "deslogado" }
  | { situacao: "erro"; mensagem: string };

/** Faz a chamada e traduz a resposta. `ler` só roda no 2xx; 204 chega sem corpo.
 *
 *  O 401 vira "deslogado" — a sessão pode ter vencido com a página aberta. Erro com `detail`
 *  em texto mostra a frase do backend, que já é escrita para o usuário. Qualquer outra coisa é o
 *  proxy sem backend, e a mensagem é a de sempre. */
async function chamar<T>(
  caminho: string,
  metodo: "GET" | "DELETE",
  ler: (corpo: unknown) => T | null,
): Promise<Resultado<T>> {
  try {
    const resposta = await fetch(caminho, { method: metodo, cache: "no-store" });
    if (resposta.status === 401) {
      return { situacao: "deslogado" };
    }
    const corpo: unknown = resposta.status === 204 ? null : await resposta.json().catch(() => null);
    if (resposta.ok) {
      const dados = ler(corpo);
      if (dados !== null) {
        return { situacao: "ok", dados };
      }
    }
    const detalhe = lerDetail(corpo);
    return {
      situacao: "erro",
      mensagem: typeof detalhe === "string" ? detalhe : MENSAGEM_SEM_SERVIDOR,
    };
  } catch {
    return { situacao: "erro", mensagem: MENSAGEM_SEM_SERVIDOR };
  }
}

function ehHistorico(corpo: unknown): corpo is Historico {
  return (
    !!corpo &&
    typeof corpo === "object" &&
    "dias" in corpo &&
    typeof corpo.dias === "number" &&
    "analises" in corpo &&
    Array.isArray(corpo.analises)
  );
}

function ehDadosConta(corpo: unknown): corpo is DadosConta {
  return (
    !!corpo &&
    typeof corpo === "object" &&
    "nome" in corpo &&
    typeof corpo.nome === "string" &&
    "email" in corpo &&
    typeof corpo.email === "string" &&
    "criado_em" in corpo &&
    typeof corpo.criado_em === "string"
  );
}

export function buscarHistorico(): Promise<Resultado<Historico>> {
  return chamar("/api/historico", "GET", (corpo) => (ehHistorico(corpo) ? corpo : null));
}

export function apagarAnalise(id: string): Promise<Resultado<true>> {
  return chamar(`/api/historico/${encodeURIComponent(id)}`, "DELETE", () => true);
}

export function apagarHistorico(): Promise<Resultado<true>> {
  return chamar("/api/historico", "DELETE", () => true);
}

export function buscarConta(): Promise<Resultado<DadosConta>> {
  return chamar("/api/conta", "GET", (corpo) => (ehDadosConta(corpo) ? corpo : null));
}

// Fuso fixo: o servidor do Render roda em UTC, e o navegador de quem viaja pode estar em outro.
// A pessoa reconhece a análise pela hora em que a fez no Brasil.
const DATA = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

const HORA = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  hour: "2-digit",
  minute: "2-digit",
});

/** "01/10/2026" */
export function formatarData(iso: string): string {
  return DATA.format(new Date(iso));
}

/** "01/10/2026 às 14:32" */
export function formatarDataHora(iso: string): string {
  const data = new Date(iso);
  return `${DATA.format(data)} às ${HORA.format(data)}`;
}
