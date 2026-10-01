"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { consultarSessao, sairDaConta, type Usuario } from "../_lib/conta";

type Sessao =
  | { situacao: "carregando" }
  | { situacao: "deslogado" }
  | { situacao: "logado"; usuario: Usuario };

const BOTAO =
  "botao-secundario alvo-de-toque inline-flex items-center rounded-full px-4 font-bold";

/** "Entrar", ou "Olá, {nome}" e "Sair". O estado vem de GET /api/auth/eu; 401 é "deslogado".
 *
 *  `aoMudarSessao` conta à página se há alguém logado — a home usa isso para o aviso do
 *  histórico, sem consultar /eu uma segunda vez. */
export function AreaSessao({ aoMudarSessao }: { aoMudarSessao?: (logado: boolean) => void }) {
  const [sessao, setSessao] = useState<Sessao>({ situacao: "carregando" });
  const [saindo, setSaindo] = useState(false);
  const [erroAoSair, setErroAoSair] = useState("");

  useEffect(() => {
    // setState dentro do `then`, não no corpo do efeito (react-hooks/set-state-in-effect); a
    // flag `ativo` descarta a resposta que chegar depois de a página sair da tela.
    let ativo = true;
    void consultarSessao().then((usuario) => {
      if (ativo) {
        setSessao(usuario ? { situacao: "logado", usuario } : { situacao: "deslogado" });
        aoMudarSessao?.(usuario !== null);
      }
    });
    return () => {
      ativo = false;
    };
    // Uma consulta por montagem: o callback novo a cada renderização da página não a repete.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function aoSair() {
    setSaindo(true);
    setErroAoSair("");
    void sairDaConta().then((saiu) => {
      setSaindo(false);
      if (saiu) {
        setSessao({ situacao: "deslogado" });
        aoMudarSessao?.(false);
      } else {
        // Continua logado na tela porque continua logado de verdade: o cookie não foi limpo.
        setErroAoSair("Não conseguimos sair. Tente de novo.");
      }
    });
  }

  return (
    <div className="flex flex-wrap items-center justify-end gap-x-2 gap-y-1">
      {/* Enquanto consulta, um espaço vazio: "Entrar" piscando para quem já está logado
          confundiria mais do que um instante sem nada. */}
      {sessao.situacao === "carregando" && <span className="inline-block min-h-[44px]" />}

      {sessao.situacao === "deslogado" && (
        <Link href="/entrar" className={BOTAO}>
          Entrar
        </Link>
      )}

      {sessao.situacao === "logado" && (
        <>
          {/* Leva à área "Minha conta" (ADR-0016), com o visual de contorno do "Sair". O nome
              tem até 60 caracteres e é cortado com reticências no <span> de dentro: no link
              (inline-flex) o `truncate` precisa de um filho que possa encolher. */}
          <Link href="/conta" className={`${BOTAO} max-w-[9rem] md:max-w-[11rem]
            xl:max-w-[14rem]`}>
            <span className="truncate">Olá, {sessao.usuario.nome}</span>
          </Link>
          <button type="button" onClick={aoSair} disabled={saindo} className={BOTAO}>
            {saindo ? "Saindo…" : "Sair"}
          </button>
        </>
      )}

      {/* Sempre montada: região criada junto com o conteúdo não é anunciada por alguns
          leitores de tela. Vazia, não ocupa espaço. */}
      <p aria-live="polite" className={erroAoSair ? "basis-full text-right font-bold" : "sr-only"}>
        {erroAoSair}
      </p>
    </div>
  );
}
