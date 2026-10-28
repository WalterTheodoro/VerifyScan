"use client";

import Link from "next/link";
import { useRef, useState } from "react";

import { AvisosDoEnvio } from "../../_componentes/avisos-do-envio";
import { MensagemColada, PrintLido, Resultado } from "../../_componentes/resultado";
import {
  apagarAnalise,
  apagarHistorico,
  buscarHistorico,
  formatarDataHora,
  type AnaliseDoHistorico,
  type Historico,
} from "../../_lib/historico";
import { partesDaTranscricao } from "../../_lib/print";
import { useCarga } from "../../_lib/use-carga";
import { AvisoEntrar } from "../aviso-entrar";

/** Qual confirmação está aberta: a de um item (pelo id) ou a de apagar tudo. */
type Confirmacao = { alvo: "uma"; id: string } | { alvo: "todas" } | null;

const BOTAO = "alvo-de-toque inline-flex items-center justify-center rounded-full px-5 font-bold";

/** Seção Histórico (RF12, ADR-0015, ADR-0018): as análises feitas logado dentro da janela, com
 *  a mensagem e o mesmo resultado da home.
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
          de ficar ligadas à sua conta, e a mensagem é apagada.
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
          {/* Um item por análise, separados por um fio: cada um já tem a placa do resultado, e
              mais um cartão em volta pesaria. */}
          <ul className="flex flex-col divide-y-2 divide-lavanda">
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
    // O mesmo resultado da home (ADR-0018): placa, "O que fazer" e fatores, de um componente só.
    <li className="flex flex-col gap-perto py-bloco first:pt-0 last:pb-0">
      <p className="text-destaque font-semibold">
        <time dateTime={analise.created_at}>{quando}</time>
      </p>

      {/* Do print, só o texto lido e o contexto: a imagem nunca foi guardada (ADR-0023). */}
      {analise.tipo_input === "imagem" && (
        <p className="font-semibold">Esta análise veio de um print.</p>
      )}
      {analise.texto !== null ? (
        <div className="flex flex-col gap-junto rounded-2xl border-2 border-lavanda p-5">
          {analise.tipo_input === "imagem" ? (
            <PrintLido
              partes={partesDaTranscricao(analise.texto)}
              contexto={analise.contexto_print ?? null}
            />
          ) : (
            <MensagemColada texto={analise.texto} />
          )}
        </div>
      ) : (
        <p>O texto desta análise não foi guardado.</p>
      )}

      <Resultado resultado={analise} nivel={3} />

      <div className="flex flex-col gap-perto">
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
