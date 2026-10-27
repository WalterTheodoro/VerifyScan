"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { AvisoAcordando } from "../_componentes/avisos-do-envio";
import { lerComRepeticao, type OpcoesDeEspera } from "../_lib/servidor";

// Página de infraestrutura, do Gate 0: prova que o frontend alcança o backend e que o backend
// alcança Postgres e Redis. Saiu de `/` na Fase 1, para dar lugar à tela de análise, e ficou
// em `/status` porque o gate continua valendo — não é tela de usuário final.

type SaudeServico = {
  // "desativado": o serviço não foi configurado de propósito (Redis sem REDIS_URL, até a Fase 4).
  status: "ok" | "erro" | "desativado";
  latencia_ms: number;
  detalhe: string | null;
};

type RespostaHealth = {
  status: "ok" | "degradado";
  postgres: SaudeServico;
  redis: SaudeServico;
};

type Estado =
  | { situacao: "carregando" }
  | { situacao: "acordando" }
  | { situacao: "carregado"; dados: RespostaHealth }
  | { situacao: "inalcancavel" };

/** Consulta a API e devolve o próximo estado. Não mexe em React — só busca e traduz.
 *
 *  A API responde 503 quando algum serviço está fora, mas o corpo tem o mesmo formato — por isso
 *  vale qualquer resposta do backend, sem checar o status code. Sem resposta do backend, repete
 *  enquanto ele acorda (ADR-0017). Caminho relativo: o Next repassa /health (ADR-0014). */
async function consultarSaude(opcoes: OpcoesDeEspera): Promise<Estado> {
  const resposta = await lerComRepeticao("/health", opcoes);
  return resposta.doBackend
    ? { situacao: "carregado", dados: resposta.corpo as RespostaHealth }
    : { situacao: "inalcancavel" };
}

export default function PaginaSaude() {
  const [estado, setEstado] = useState<Estado>({ situacao: "carregando" });
  // Uma consulta por vez: "Verificar novamente" cancela a anterior, e sair da página também.
  const consultaAtual = useRef<AbortController | null>(null);

  // O setState fica nos callbacks, não no corpo do efeito: chamado de forma síncrona ali, ele
  // dispararia renderização em cascata (react-hooks/set-state-in-effect). O abort descarta a
  // resposta que chegar depois de a consulta ser substituída ou de a página sair da tela.
  const consultar = useCallback(() => {
    consultaAtual.current?.abort();
    const controle = new AbortController();
    consultaAtual.current = controle;
    void consultarSaude({
      aoEsperar: () => setEstado({ situacao: "acordando" }),
      signal: controle.signal,
    }).then((resultado) => {
      if (!controle.signal.aborted) {
        setEstado(resultado);
      }
    });
  }, []);

  useEffect(() => {
    consultar();
    return () => consultaAtual.current?.abort();
  }, [consultar]);

  function aoClicarVerificar() {
    setEstado({ situacao: "carregando" });
    consultar();
  }

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-bold">VerifyScan — estado da infraestrutura</h1>
        <p className="text-sm opacity-70">
          Consultando <code>/health</code> (repassado ao backend)
        </p>
      </header>

      {estado.situacao === "carregando" && <p>Consultando a API…</p>}

      {estado.situacao === "acordando" && <AvisoAcordando />}

      {estado.situacao === "inalcancavel" && (
        <div className="border border-current p-4">
          <p className="font-bold">Não conseguimos falar com o servidor.</p>
          {/* A dica é para quem desenvolve: em produção, o visitante vê só a frase acima.
              `--loop none`: no Windows, o loop padrão quebra o psycopg assíncrono (ADR-0007). */}
          {process.env.NODE_ENV !== "production" && (
            <p className="text-sm">
              O backend está no ar?{" "}
              <code>uv run uvicorn app.main:app --port 8000 --loop none</code>
            </p>
          )}
        </div>
      )}

      {estado.situacao === "carregado" && (
        <div className="flex flex-col gap-4">
          <p>
            Estado geral: <strong>{estado.dados.status}</strong>
          </p>
          <ul className="flex flex-col gap-3">
            <CartaoServico nome="PostgreSQL" saude={estado.dados.postgres} />
            <CartaoServico nome="Redis" saude={estado.dados.redis} />
          </ul>
        </div>
      )}

      <button
        type="button"
        onClick={aoClicarVerificar}
        className="self-start border border-current px-4 py-2"
      >
        Verificar novamente
      </button>
    </main>
  );
}

function CartaoServico({ nome, saude }: { nome: string; saude: SaudeServico }) {
  // O estado nunca é comunicado só por cor — o texto "ok"/"erro" carrega a informação sozinho.
  // As regras de acessibilidade do ADR-0010 valem para a tela de análise; esta é diagnóstico.
  if (saude.status === "desativado") {
    // Tom neutro: desativado é configuração, não falha — o /health continua "ok".
    return (
      <li className="border border-current p-4 opacity-70">
        <p>
          <strong>{nome}:</strong> desativado até a Fase 4
        </p>
      </li>
    );
  }
  return (
    <li className="border border-current p-4">
      <p>
        <strong>{nome}:</strong> {saude.status} ({saude.latencia_ms} ms)
      </p>
      {saude.detalhe && <p className="mt-1 text-sm opacity-70">{saude.detalhe}</p>}
    </li>
  );
}
