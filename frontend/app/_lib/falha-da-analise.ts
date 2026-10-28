// A frase que a tela mostra quando a análise não sai (correção 9.1). "Verifique sua conexão" só
// quando não houve resposta nenhuma: com resposta, o problema não é a conexão da pessoa, e a frase
// do servidor diz o que fazer ("grande demais", "não conseguimos ler uma conversa").
//
// Sem imports de valor, para o teste rodar no Node direto; o `import type` some no type stripping.

import type { Resposta } from "./servidor";

export const SEM_CONEXAO =
  "Não conseguimos falar com o serviço de análise. Verifique sua conexão e tente de novo.";

// A mesma frase do 413 do backend (`app/api/analises.py`), para quando o 413 chega sem o JSON.
const GRANDE_DEMAIS = "Esta imagem é grande demais. Envie um print da tela, sem ampliar.";

const TENTE_DE_NOVO =
  "Não conseguimos analisar esta mensagem agora. Tente de novo em alguns instantes.";

export function fraseDaFalha(resposta: Resposta): string {
  if (resposta.doBackend) {
    // `detail` em string é recusa de regra de negócio, já escrita para a pessoa. Em lista, é o
    // formato do FastAPI, que não serve para exibir.
    const corpo = resposta.corpo;
    if (corpo && typeof corpo === "object" && "detail" in corpo) {
      if (typeof corpo.detail === "string") {
        return corpo.detail;
      }
    }
  } else if (resposta.status === undefined) {
    return SEM_CONEXAO;
  }
  return resposta.status === 413 ? GRANDE_DEMAIS : TENTE_DE_NOVO;
}
