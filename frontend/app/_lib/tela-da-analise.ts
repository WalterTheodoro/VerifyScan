// O estado da tela de análise num reducer puro (correção 9.1): o print escolhido, o aviso do
// preparo e o estado do envio. É aqui, e não espalhado pelos handlers da página, que se decide
// quando o erro anterior sai da tela — e por isso dá para testar no Node, sem navegador.
//
// Genérico no resultado (R) e na imagem (I): os tipos de verdade moram na página e em
// `imagem.ts`, e este arquivo não importa nada, como os outros testados com `node:test`.

export type Estado<R> =
  | { situacao: "pronta" }
  | { situacao: "analisando"; doPrint: boolean }
  | { situacao: "concluida"; resultado: R }
  | { situacao: "falhou"; mensagem: string };

export type Tela<R, I> = {
  estado: Estado<R>;
  /** O print escolhido, já reduzido e sem metadados. Um por análise: outro substitui este. */
  imagem: I | null;
  preparando: boolean;
  /** Por que o print não entrou ("envie PNG, JPEG ou WebP", "pequena demais"). */
  aviso: string | null;
};

export type Acao<R, I> =
  /** Escolheu pelo botão, colou ou soltou um arquivo. */
  | { tipo: "escolheu" }
  | { tipo: "preparou"; imagem: I }
  | { tipo: "nao-preparou"; mensagem: string }
  | { tipo: "removeu" }
  | { tipo: "digitou" }
  | { tipo: "enviou" }
  | { tipo: "respondeu"; estado: Estado<R> }
  /** "Analisar outra mensagem". */
  | { tipo: "recomecou" };

export const TELA_INICIAL: Tela<never, never> = {
  estado: { situacao: "pronta" },
  imagem: null,
  preparando: false,
  aviso: null,
};

/** O erro do envio sai da tela; qualquer outro estado fica como está. */
function semFalha<R>(estado: Estado<R>): Estado<R> {
  return estado.situacao === "falhou" ? { situacao: "pronta" } : estado;
}

export function proximaTela<R, I>(tela: Tela<R, I>, acao: Acao<R, I>): Tela<R, I> {
  switch (acao.tipo) {
    case "escolheu":
      return { ...tela, estado: semFalha(tela.estado), aviso: null, preparando: true };
    case "preparou":
      return { ...tela, imagem: acao.imagem, preparando: false };
    case "nao-preparou":
      return { ...tela, aviso: acao.mensagem, preparando: false };
    case "removeu":
      return { ...tela, estado: semFalha(tela.estado), imagem: null, aviso: null };
    case "digitou":
      return { ...tela, aviso: null };
    case "enviou":
      return {
        ...tela,
        estado: { situacao: "analisando", doPrint: tela.imagem !== null },
        aviso: null,
      };
    case "respondeu":
      return { ...tela, estado: acao.estado };
    case "recomecou":
      return TELA_INICIAL;
  }
}
