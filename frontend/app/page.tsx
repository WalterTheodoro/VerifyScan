"use client";

import { useRef, useState } from "react";

// Tela de análise e tela de resultado (Telas 1 e 3 do RFC §4.2), numa página só.
//
// Numa página só, e não em duas rotas, por um motivo de privacidade: passar a mensagem para
// /resultado exigiria colocá-la na URL ou em storage do navegador. A mensagem do usuário não
// sai da memória da aba.

const URL_API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type NivelRisco = "BAIXO" | "MEDIO" | "ALTO";

type Fator = {
  tipo: string;
  categoria: string;
  descricao: string;
  peso: number;
};

type RespostaAnalise = {
  score: number;
  nivel_risco: NivelRisco;
  fatores: Fator[];
  urls_analisadas: string[];
  explicacao_indisponivel: boolean;
  verificacao_externa_indisponivel: boolean;
};

type Estado =
  | { situacao: "pronta" }
  | { situacao: "analisando" }
  | { situacao: "concluida"; resultado: RespostaAnalise }
  | { situacao: "falhou"; mensagem: string };

/** Texto exibido para cada nível. Nunca só a cor: a palavra e o ícone carregam o sentido. */
const APRESENTACAO: Record<
  NivelRisco,
  { palavra: string; resumo: string; recomendacao: string }
> = {
  BAIXO: {
    palavra: "Risco baixo",
    resumo: "Não encontramos sinais de golpe nesta mensagem.",
    recomendacao:
      "Mesmo assim, se a mensagem pedir dinheiro ou dados, procure a empresa pelo telefone " +
      "ou aplicativo oficial antes de responder.",
  },
  MEDIO: {
    palavra: "Risco médio",
    resumo: "Esta mensagem tem sinais que merecem atenção.",
    recomendacao:
      "Não clique em links e não informe seus dados. Procure a empresa pelo telefone ou " +
      "aplicativo oficial para confirmar se a mensagem é verdadeira.",
  },
  ALTO: {
    palavra: "Risco alto",
    resumo: "Esta mensagem tem sinais fortes de golpe.",
    recomendacao:
      "Não clique no link, não faça nenhum pagamento e não informe seus dados. Apague a " +
      "mensagem e bloqueie quem enviou.",
  },
};

/** Manda o texto para a API e traduz qualquer falha em uma frase que o usuário entenda. */
async function analisar(texto: string): Promise<Estado> {
  try {
    const resposta = await fetch(`${URL_API}/api/analises`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ texto }),
    });

    if (resposta.ok) {
      return { situacao: "concluida", resultado: (await resposta.json()) as RespostaAnalise };
    }

    // A API devolve `detail` como string quando a recusa é uma regra de negócio — e essa
    // string já é a mensagem escrita para o usuário. Nos outros casos o formato é do FastAPI
    // e não serve para exibir.
    const corpo: unknown = await resposta.json().catch(() => null);
    const detalhe =
      corpo && typeof corpo === "object" && "detail" in corpo ? corpo.detail : null;
    return {
      situacao: "falhou",
      mensagem:
        typeof detalhe === "string"
          ? detalhe
          : "Não conseguimos analisar esta mensagem agora. Tente de novo em alguns instantes.",
    };
  } catch {
    return {
      situacao: "falhou",
      mensagem:
        "Não conseguimos falar com o serviço de análise. Verifique sua conexão e tente de novo.",
    };
  }
}

export default function PaginaAnalise() {
  const [texto, setTexto] = useState("");
  const [estado, setEstado] = useState<Estado>({ situacao: "pronta" });
  const tituloDoResultado = useRef<HTMLHeadingElement>(null);

  function aoEnviar(evento: React.FormEvent) {
    evento.preventDefault();
    setEstado({ situacao: "analisando" });
    void analisar(texto).then((proximo) => {
      setEstado(proximo);
      // Leva o foco para o resultado: sem isso, quem usa teclado ou leitor de tela continua
      // no botão e não percebe que a resposta chegou.
      requestAnimationFrame(() => tituloDoResultado.current?.focus());
    });
  }

  function aoRecomecar() {
    setTexto("");
    setEstado({ situacao: "pronta" });
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-5 py-10">
      <header className="flex flex-col gap-3">
        <h1 className="text-3xl font-bold">Recebeu uma mensagem estranha?</h1>
        <p className="text-[var(--texto-secundario)]">
          Cole a mensagem aqui embaixo. Vamos dizer se ela tem sinais de golpe e o que fazer.
        </p>
      </header>

      <form onSubmit={aoEnviar} className="flex flex-col gap-4">
        <label htmlFor="mensagem" className="text-xl font-semibold">
          Cole aqui a mensagem que você recebeu
        </label>
        <textarea
          id="mensagem"
          name="mensagem"
          value={texto}
          onChange={(evento) => setTexto(evento.target.value)}
          rows={8}
          placeholder="Exemplo: sua conta será bloqueada hoje, faça um PIX para regularizar…"
          className="w-full rounded-lg border-2 border-[var(--borda)] bg-white p-4 text-lg
            placeholder:text-[var(--texto-secundario)]"
        />
        <div className="flex flex-wrap items-center gap-4">
          <button
            type="submit"
            disabled={texto.trim() === "" || estado.situacao === "analisando"}
            className="alvo-de-toque rounded-lg bg-[var(--acao)] px-7 py-3 text-lg font-semibold
              text-white hover:bg-[var(--acao-escura)] disabled:cursor-not-allowed
              disabled:bg-[var(--texto-secundario)]"
          >
            {estado.situacao === "analisando" ? "Analisando…" : "Analisar agora"}
          </button>
          {estado.situacao === "concluida" && (
            <button
              type="button"
              onClick={aoRecomecar}
              className="alvo-de-toque rounded-lg border-2 border-[var(--acao)] px-7 py-3
                text-lg font-semibold text-[var(--acao)] hover:bg-[var(--fundo-suave)]"
            >
              Analisar outra mensagem
            </button>
          )}
        </div>
      </form>

      {/* `aria-live` faz o leitor de tela anunciar o resultado sem que a pessoa precise
          procurá-lo. `polite` para não interromper o que estiver sendo lido. */}
      <section aria-live="polite" className="flex flex-col gap-6">
        {estado.situacao === "analisando" && (
          <p className="text-xl">Analisando sua mensagem…</p>
        )}

        {estado.situacao === "falhou" && (
          <div
            role="alert"
            className="rounded-lg border-2 border-l-[10px] border-[var(--erro)] bg-[#fef2f2] p-5"
          >
            <p className="text-lg font-semibold">Não deu para analisar</p>
            <p className="mt-1">{estado.mensagem}</p>
          </div>
        )}

        {estado.situacao === "concluida" && (
          <Resultado resultado={estado.resultado} tituloRef={tituloDoResultado} />
        )}
      </section>
    </main>
  );
}

function Resultado({
  resultado,
  tituloRef,
}: {
  resultado: RespostaAnalise;
  tituloRef: React.RefObject<HTMLHeadingElement | null>;
}) {
  const { palavra, resumo, recomendacao } = APRESENTACAO[resultado.nivel_risco];

  return (
    <div className="painel-risco flex flex-col gap-5 p-6" data-nivel={resultado.nivel_risco}>
      <div className="flex items-center gap-4">
        {/* O ícone é decorativo para o leitor de tela: a palavra ao lado já diz tudo, e
            anunciar os dois seria repetição. */}
        <span
          aria-hidden="true"
          className="cracha-risco flex h-14 w-14 shrink-0 items-center justify-center
            rounded-full"
        >
          <IconeDeRisco nivel={resultado.nivel_risco} />
        </span>
        <h2
          ref={tituloRef}
          tabIndex={-1}
          className="text-3xl font-bold text-[var(--risco-forte)]"
        >
          {palavra}
        </h2>
      </div>

      <p className="text-xl">{resumo}</p>

      {resultado.fatores.length > 0 && (
        <div className="flex flex-col gap-3">
          <h3 className="text-xl font-semibold">Fatores identificados</h3>
          <ul className="flex flex-col gap-3">
            {resultado.fatores.map((fator) => (
              <li
                key={fator.categoria}
                className="flex gap-3 rounded-lg bg-white/70 p-4 text-lg"
              >
                <span aria-hidden="true" className="text-[var(--risco-forte)]">
                  •
                </span>
                {fator.descricao}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-col gap-2 border-t-2 border-[var(--risco-forte)] pt-5">
        <h3 className="text-xl font-semibold">O que fazer</h3>
        <p className="text-lg">{recomendacao}</p>
      </div>
    </div>
  );
}

function IconeDeRisco({ nivel }: { nivel: NivelRisco }) {
  const comum = {
    width: 30,
    height: 30,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2.5,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };

  if (nivel === "BAIXO") {
    return (
      <svg {...comum}>
        <path d="M20 6 9 17l-5-5" />
      </svg>
    );
  }
  if (nivel === "MEDIO") {
    return (
      <svg {...comum}>
        <path d="M12 3 2 20h20L12 3Z" />
        <path d="M12 10v4" />
        <path d="M12 17.5v.01" />
      </svg>
    );
  }
  return (
    <svg {...comum}>
      <circle cx="12" cy="12" r="9" />
      <path d="m15 9-6 6" />
      <path d="m9 9 6 6" />
    </svg>
  );
}
