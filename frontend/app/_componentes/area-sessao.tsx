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

/** "Entrar", ou "Olá, {nome}" e "Sair". O estado vem de GET /api/auth/eu; 401 é "deslogado". */
export function AreaSessao() {
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
      }
    });
    return () => {
      ativo = false;
    };
  }, []);

  function aoSair() {
    setSaindo(true);
    setErroAoSair("");
    void sairDaConta().then((saiu) => {
      setSaindo(false);
      if (saiu) {
        setSessao({ situacao: "deslogado" });
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
          {/* O nome tem até 60 caracteres e é cortado com reticências. Medido no navegador
              (rem de 18 px): 9rem cabe com "Sair" em 320 px; 11rem deixa a sessão na mesma
              linha em 768 px, com 18 px de folga; 14rem é o desktop, igual ao de antes. */}
          <span className="max-w-[9rem] truncate font-semibold md:max-w-[11rem]
            xl:max-w-[14rem]">
            Olá, {sessao.usuario.nome}
          </span>
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
