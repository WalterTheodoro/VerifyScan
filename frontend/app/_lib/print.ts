// O que a tela mostra de um print lido (fatia 9, ADR-0023): a transcrição e o contexto, em
// frases simples, para a pessoa conferir se lemos certo. Sem imports, para o teste rodar no Node.

export type QuemMandou = "contato" | "pessoa" | "nao_da_para_saber";

export type MensagemDoPrint = { de: QuemMandou; texto: string };

export type ContextoDoPrint = {
  canal: "whatsapp" | "sms" | "email" | "instagram" | "outro" | "nao_identificado";
  remetente_salvo: "sim" | "nao" | "nao_da_para_saber";
  aviso_do_app: "sim" | "nao";
  primeira_mensagem: "sim" | "nao" | "nao_da_para_saber";
  tem_link_visivel: "sim" | "nao";
};

export type LeituraDoPrint = {
  mensagens: MensagemDoPrint[];
  contexto: ContextoDoPrint;
  texto_da_pessoa: string | null;
};

/** Quem mandou, como a tela escreve antes de cada mensagem. */
export const ROTULO_DE_QUEM_MANDOU: Record<QuemMandou | "escrito", string> = {
  contato: "Você recebeu:",
  pessoa: "Você enviou:",
  nao_da_para_saber: "Não deu para ver quem mandou:",
  escrito: "Você escreveu junto:",
};

/** O contexto em frases do dia a dia. Só o que ajuda a conferir: "não" e "não deu para saber"
 *  de alguns campos não viram frase, para a lista não ficar comprida. */
export function frasesDoContexto(contexto: ContextoDoPrint): string[] {
  const frases: string[] = [];
  const canal: Record<ContextoDoPrint["canal"], string | null> = {
    whatsapp: "Parece ser uma conversa de WhatsApp.",
    sms: "Parece ser um SMS.",
    email: "Parece ser um e-mail.",
    instagram: "Parece ser uma mensagem do Instagram.",
    outro: "Parece ser um aplicativo de mensagens.",
    nao_identificado: null,
  };
  const frasesDoCanal = canal[contexto.canal];
  if (frasesDoCanal) {
    frases.push(frasesDoCanal);
  }
  if (contexto.remetente_salvo === "sim") {
    frases.push("Quem mandou aparece com um nome salvo nos seus contatos.");
  } else if (contexto.remetente_salvo === "nao") {
    frases.push(
      contexto.canal === "email"
        ? "Quem mandou não está nos seus contatos."
        : "O número não está salvo nos seus contatos.",
    );
  }
  if (contexto.aviso_do_app === "sim") {
    frases.push("O aplicativo mostrou um aviso sobre quem mandou.");
  }
  if (contexto.primeira_mensagem === "sim") {
    frases.push("Parece ser a primeira mensagem dessa conversa.");
  } else if (contexto.primeira_mensagem === "nao") {
    frases.push("A conversa já tinha mensagens antes.");
  }
  if (contexto.tem_link_visivel === "sim") {
    frases.push("Aparece um link no print.");
  }
  return frases;
}

// As marcas da transcrição guardada no histórico, iguais às de `app/ocr/leitura.py`.
const MARCAS: Record<string, QuemMandou | "escrito"> = {
  "[recebida]": "contato",
  "[enviada pela pessoa]": "pessoa",
  "[remetente incerto]": "nao_da_para_saber",
  "[a pessoa também escreveu]": "escrito",
};

export type ParteDaTranscricao = { de: QuemMandou | "escrito"; texto: string };

/** Desfaz a transcrição marcada que o histórico guarda. Texto sem marca volta numa parte só,
 *  como recebido: é o que acontece com as análises de texto colado. */
export function partesDaTranscricao(texto: string): ParteDaTranscricao[] {
  const partes: ParteDaTranscricao[] = [];
  let atual: ParteDaTranscricao | null = null;
  for (const linha of texto.split("\n")) {
    const marca = MARCAS[linha.trim()];
    if (marca) {
      atual = { de: marca, texto: "" };
      partes.push(atual);
      continue;
    }
    if (!atual) {
      atual = { de: "contato", texto: "" };
      partes.push(atual);
    }
    atual.texto = atual.texto ? `${atual.texto}\n${linha}` : linha;
  }
  return partes
    .map((parte) => ({ ...parte, texto: parte.texto.trim() }))
    .filter((parte) => parte.texto !== "");
}
