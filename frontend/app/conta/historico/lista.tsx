"use client";

import Link from "next/link";
import { useRef, useState } from "react";

import { AvisosDoEnvio } from "../../_componentes/avisos-do-envio";
import { IconeDeRisco, PALAVRA_DO_NIVEL } from "../../_componentes/nivel-risco";
import {
  apagarAnalise,
  apagarHistorico,
  buscarHistorico,
  formatarDataHora,
  type AnaliseDoHistorico,
  type Historico,
} from "../../_lib/historico";
import { useCarga } from "../../_lib/use-carga";
import { AvisoEntrar } from "../aviso-entrar";

/** Qual confirmação está aberta: a de um item (pelo id) ou a de apagar tudo. */
type Confirmacao = { alvo: "uma"; id: string } | { alvo: "todas" } | null;

const BOTAO = "alvo-de-toque inline-flex items-center justify-center rounded-full px-5 font-bold";

/** Seção Histórico (RF12, ADR-0015): as análises feitas logado dentro da janela, sem o texto.
 *
 *  Apagar pede confirmação na própria linha, sem janela por cima: modal exige prender o foco, e
 *  `window.confirm` tem redação do navegador, não a nossa. */
export function ListaDoHistorico() {
  const { carga, definir, demorando } = useCarga(buscarHistorico);
  const [confirmacao, setConfirmacao] = useState<Confirmacao>(null);
  const [apagando, setApagando] = useState(false);
  const [anuncio, setAnuncio] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const avisoDeErro = useRef<HTMLDivElement>(null);
  const titulo = useRef<HTMLHeadingElement>(null);
  const cancelar = useRef<HTMLButtonElement>(null);

  function abrirConfirmacao(proxima: Confirmacao) {
    setConfirmacao(proxima);
    setAnuncio("");
    setErro(null);
    // O foco vai para "Cancelar": Enter sem querer não apaga nada.
    requestAnimationFrame(() => cancelar.current?.focus());
  }

  function confirmar(historico: Historico) {
    if (confirmacao === null) {
      return;
    }
    const alvo = confirmacao;
    setApagando(true);
    const pedido = alvo.alvo === "uma" ? apagarAnalise(alvo.id) : apagarHistorico();
    void pedido.then((resultado) => {
      setApagando(false);
      setConfirmacao(null);
      if (resultado.situacao === "deslogado") {
        definir({ situacao: "deslogado" });
        return;
      }
      if (resultado.situacao === "erro") {
        setErro(resultado.mensagem);
        requestAnimationFrame(() => avisoDeErro.current?.focus());
        return;
      }
      const restantes =
        alvo.alvo === "uma" ? historico.analises.filter((a) => a.id !== alvo.id) : [];
      definir({ situacao: "ok", dados: { ...historico, analises: restantes } });
      setAnuncio(alvo.alvo === "uma" ? "Análise apagada." : "Histórico apagado.");
      // O item clicado sumiu junto com o foco; o título da lista é o ponto de retorno.
      requestAnimationFrame(() => titulo.current?.focus());
    });
  }

  if (carga.situacao === "deslogado") {
    return <AvisoEntrar />;
  }

  const historico = carga.situacao === "ok" ? carga.dados : null;
  const erroDaCarga = carga.situacao === "erro" ? carga.mensagem : null;

  return (
    <section aria-labelledby="titulo-historico" className="flex flex-col gap-bloco">
      <div className="flex flex-col gap-junto">
        <h2 id="titulo-historico" ref={titulo} tabIndex={-1}
          className="text-secao font-bold sm:text-secao-lg">
          Histórico
        </h2>
        <p>
          Mostramos as análises dos últimos {historico?.dias ?? 7} dias. Depois disso, elas deixam
          de ficar ligadas à sua conta.
        </p>
        {/* Sempre montadas: região criada junto com o conteúdo não é anunciada por alguns
            leitores de tela. Ficam neste grupo, de espaçamento curto, porque vazias também
            contam no espaçamento do flex. */}
        <p aria-live="polite" className={anuncio ? "font-semibold" : "sr-only"}>
          {anuncio}
        </p>
        <AvisosDoEnvio demorando={demorando} erro={erro ?? erroDaCarga}
          avisoDeErro={avisoDeErro} />
      </div>

      {carga.situacao === "carregando" && !demorando && <p>Carregando o histórico…</p>}

      {historico && historico.analises.length === 0 && (
        <div className="flex flex-col gap-perto">
          <p className="text-destaque">
            Você ainda não fez nenhuma análise nos últimos {historico.dias} dias.
          </p>
          <Link href="/#analisar" className="font-bold text-anil underline underline-offset-4">
            Analisar uma mensagem
          </Link>
        </div>
      )}

      {historico && historico.analises.length > 0 && (
        <>
          <ul className="flex flex-col gap-perto">
            {historico.analises.map((analise) => (
              <ItemDoHistorico
                key={analise.id}
                analise={analise}
                confirmando={confirmacao?.alvo === "uma" && confirmacao.id === analise.id}
                apagando={apagando}
                cancelarRef={cancelar}
                aoPedirApagar={() => abrirConfirmacao({ alvo: "uma", id: analise.id })}
                aoConfirmar={() => confirmar(historico)}
                aoCancelar={() => setConfirmacao(null)}
              />
            ))}
          </ul>

          <div className="flex flex-col gap-perto border-t-2 border-lavanda pt-bloco">
            {confirmacao?.alvo === "todas" ? (
              <Confirmar
                pergunta="Apagar todo o histórico? Não dá para desfazer."
                rotuloSim="Sim, apagar tudo"
                apagando={apagando}
                cancelarRef={cancelar}
                aoConfirmar={() => confirmar(historico)}
                aoCancelar={() => setConfirmacao(null)}
              />
            ) : (
              <button type="button" onClick={() => abrirConfirmacao({ alvo: "todas" })}
                className={`${BOTAO} botao-secundario self-start`}>
                Apagar todo o histórico
              </button>
            )}
          </div>
        </>
      )}
    </section>
  );
}

function ItemDoHistorico({
  analise,
  confirmando,
  apagando,
  cancelarRef,
  aoPedirApagar,
  aoConfirmar,
  aoCancelar,
}: {
  analise: AnaliseDoHistorico;
  confirmando: boolean;
  apagando: boolean;
  cancelarRef: React.RefObject<HTMLButtonElement | null>;
  aoPedirApagar: () => void;
  aoConfirmar: () => void;
  aoCancelar: () => void;
}) {
  const quando = formatarDataHora(analise.created_at);

  return (
    // As cores do nível vêm do mesmo `.placa-risco[data-nivel]` do resultado da home.
    <li className="placa-risco rounded-2xl border-2 border-[var(--risco-forte)]"
      data-nivel={analise.nivel_risco}>
      <div className="faixa-risco flex items-center gap-3 px-5 py-3">
        <span aria-hidden="true" className="shrink-0">
          <IconeDeRisco nivel={analise.nivel_risco} tamanho={32} />
        </span>
        <h3 className="text-secao font-bold">{PALAVRA_DO_NIVEL[analise.nivel_risco]}</h3>
      </div>

      <div className="flex flex-col gap-perto p-5">
        <p className="flex flex-wrap gap-x-perto">
          <time dateTime={analise.created_at} className="font-semibold">{quando}</time>
          <span>Pontuação: {analise.score_risco}</span>
        </p>

        {analise.fatores.length > 0 ? (
          <ul className="flex list-disc flex-col gap-1 pl-6 marker:text-[var(--risco-forte)]">
            {analise.fatores.map((fator) => (
              <li key={fator.categoria}>{fator.descricao}</li>
            ))}
          </ul>
        ) : (
          <p>Nenhum sinal conhecido de golpe foi encontrado.</p>
        )}

        {confirmando ? (
          <Confirmar
            pergunta="Apagar esta análise?"
            rotuloSim="Sim, apagar"
            apagando={apagando}
            cancelarRef={cancelarRef}
            aoConfirmar={aoConfirmar}
            aoCancelar={aoCancelar}
          />
        ) : (
          // O nome acessível começa pelo texto visível (WCAG 2.5.3) e diz qual análise é.
          <button type="button" onClick={aoPedirApagar} aria-label={`Apagar a análise de ${quando}`}
            className={`${BOTAO} botao-secundario self-start`}>
            Apagar
          </button>
        )}
      </div>
    </li>
  );
}

function Confirmar({
  pergunta,
  rotuloSim,
  apagando,
  cancelarRef,
  aoConfirmar,
  aoCancelar,
}: {
  pergunta: string;
  rotuloSim: string;
  apagando: boolean;
  cancelarRef: React.RefObject<HTMLButtonElement | null>;
  aoConfirmar: () => void;
  aoCancelar: () => void;
}) {
  return (
    <div role="group" aria-label={pergunta} className="flex flex-col gap-junto">
      <p className="font-bold">{pergunta}</p>
      <div className="flex flex-wrap gap-junto">
        <button type="button" onClick={aoConfirmar} disabled={apagando}
          className={`${BOTAO} botao-principal`}>
          {apagando ? "Apagando…" : rotuloSim}
        </button>
        <button type="button" ref={cancelarRef} onClick={aoCancelar} disabled={apagando}
          className={`${BOTAO} botao-secundario`}>
          Cancelar
        </button>
      </div>
    </div>
  );
}
