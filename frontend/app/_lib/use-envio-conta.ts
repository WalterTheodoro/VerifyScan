import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { enviarConta } from "./conta";

// Depois disto sem resposta, avisa que o servidor está acordando: no plano gratuito o backend
// dorme e leva até ~60 s para voltar, e o público não pode achar que a tela travou.
export const ESPERA_ATE_AVISAR_MS = 5000;

/** Envio comum a /entrar e /cadastro: estado de envio, aviso de demora, erro e redirecionamento. */
export function useEnvioConta(caminho: "/api/auth/cadastro" | "/api/auth/login") {
  const router = useRouter();
  const [enviando, setEnviando] = useState(false);
  const [demorando, setDemorando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const avisoDeErro = useRef<HTMLDivElement>(null);

  function enviar(corpo: Record<string, string>) {
    setEnviando(true);
    setDemorando(false);
    setErro(null);
    // O timer nasce no envio, não num efeito: é consequência do clique, não da renderização.
    const timer = window.setTimeout(() => setDemorando(true), ESPERA_ATE_AVISAR_MS);

    void enviarConta(caminho, corpo).then((resultado) => {
      window.clearTimeout(timer);
      setDemorando(false);
      if (resultado.ok) {
        // O botão segue em "Entrando…" até a home abrir; lá o cabeçalho consulta /eu de novo.
        router.push("/");
        return;
      }
      setEnviando(false);
      setErro(resultado.mensagem);
      // Leva o foco ao erro: quem usa teclado ou leitor de tela continuaria no botão.
      requestAnimationFrame(() => avisoDeErro.current?.focus());
    });
  }

  return { enviando, demorando, erro, avisoDeErro, enviar };
}
