"use client";

import { useEffect, useState } from "react";

// Página de infraestrutura, do Gate 0: prova que o frontend alcança o backend e que o backend
// alcança Postgres e Redis. Saiu de `/` na Fase 1, para dar lugar à tela de análise, e ficou
// em `/status` porque o gate continua valendo — não é tela de usuário final.

const URL_API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type SaudeServico = {
  status: "ok" | "erro";
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
  | { situacao: "carregado"; dados: RespostaHealth }
  | { situacao: "inalcancavel"; erro: string };

/** Consulta a API e devolve o próximo estado. Não mexe em React — só busca e traduz. */
async function consultarSaude(): Promise<Estado> {
  try {
    // A API responde 503 quando algum serviço está fora, mas o corpo tem o mesmo formato —
    // por isso lemos o JSON sem checar o status code.
    const resposta = await fetch(`${URL_API}/health`, { cache: "no-store" });
    const dados = (await resposta.json()) as RespostaHealth;
    return { situacao: "carregado", dados };
  } catch (erro) {
    return {
      situacao: "inalcancavel",
      erro: erro instanceof Error ? erro.message : "erro desconhecido",
    };
  }
}

export default function PaginaSaude() {
  const [estado, setEstado] = useState<Estado>({ situacao: "carregando" });

  useEffect(() => {
    // O setState fica dentro do callback do `then`, não no corpo do efeito: chamado de forma
    // síncrona ali, ele dispararia renderização em cascata (react-hooks/set-state-in-effect).
    // A flag `ativo` descarta a resposta que chegar depois de a página sair da tela.
    let ativo = true;
    void consultarSaude().then((resultado) => {
      if (ativo) {
        setEstado(resultado);
      }
    });
    return () => {
      ativo = false;
    };
  }, []);

  function aoClicarVerificar() {
    setEstado({ situacao: "carregando" });
    void consultarSaude().then(setEstado);
  }

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-bold">VerifyScan — estado da infraestrutura</h1>
        <p className="text-sm opacity-70">
          Consultando <code>{URL_API}/health</code>
        </p>
      </header>

      {estado.situacao === "carregando" && <p>Consultando a API…</p>}

      {estado.situacao === "inalcancavel" && (
        <div className="border border-current p-4">
          <p className="font-bold">API inalcançável</p>
          <p className="text-sm">
            O backend está no ar? <code>uv run uvicorn app.main:app --reload --port 8000</code>
          </p>
          <p className="mt-2 text-sm opacity-70">{estado.erro}</p>
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
  return (
    <li className="border border-current p-4">
      <p>
        <strong>{nome}:</strong> {saude.status} ({saude.latencia_ms} ms)
      </p>
      {saude.detalhe && <p className="mt-1 text-sm opacity-70">{saude.detalhe}</p>}
    </li>
  );
}
