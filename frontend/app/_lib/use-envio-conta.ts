import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { enviarConta } from "./conta";
import type { OpcoesDeEspera } from "./servidor";

// Depois disto sem resposta, avisa que o servidor está acordando: no plano gratuito o backend
// dorme e leva até ~60 s para voltar, e o público não pode achar que a tela travou.
export const ESPERA_ATE_AVISAR_MS = 5000;

/** O que todo envio das telas de conta tem em comum: o estado de envio, o aviso de demora, o
 *  erro e o foco nele. Entrar, cadastro, trocar senha e excluir conta usam este hook; o que fazer
 *  com a resposta fica com cada tela. */
export function useEnvio() {
  const [enviando, setEnviando] = useState(false);
  const [demorando, setDemorando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const avisoDeErro = useRef<HTMLDivElement>(null);

  /** Roda o envio com o aviso de demora. O botão continua em "enviando" até a tela chamar
   *  `falhar` ou `concluir`: no login, ele segue assim até a home abrir. */
  async function enviar<T>(acao: (opcoes: OpcoesDeEspera) => Promise<T>): Promise<T> {
    setEnviando(true);
    setDemorando(false);
    setErro(null);
    // O timer nasce no envio, não num efeito: é consequência do clique, não da renderização.
    // `aoEsperar` liga o aviso antes, se o envio tiver de esperar o backend acordar (ADR-0017).
    const timer = window.setTimeout(() => setDemorando(true), ESPERA_ATE_AVISAR_MS);
    try {
      return await acao({ aoEsperar: () => setDemorando(true) });
    } finally {
      window.clearTimeout(timer);
      setDemorando(false);
    }
  }

  function falhar(mensagem: string) {
    setEnviando(false);
    setErro(mensagem);
    // Leva o foco ao erro: quem usa teclado ou leitor de tela continuaria no botão.
    requestAnimationFrame(() => avisoDeErro.current?.focus());
  }

  function concluir() {
    setEnviando(false);
  }

  return { enviando, demorando, erro, avisoDeErro, enviar, falhar, concluir };
}

/** Envio comum a /entrar e /cadastro: em caso de sucesso, vai para a home. */
export function useEnvioConta(caminho: "/api/auth/cadastro" | "/api/auth/login") {
  const router = useRouter();
  const { enviando, demorando, erro, avisoDeErro, enviar, falhar } = useEnvio();

  function enviarCorpo(corpo: Record<string, string>) {
    void enviar((opcoes) => enviarConta(caminho, corpo, opcoes)).then((resultado) => {
      if (resultado.ok) {
        // O botão segue em "Entrando…" até a home abrir; lá o cabeçalho consulta /eu de novo.
        router.push("/");
        return;
      }
      falhar(resultado.mensagem);
    });
  }

  return { enviando, demorando, erro, avisoDeErro, enviar: enviarCorpo };
}
