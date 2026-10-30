"use client";

import Link from "next/link";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import { AvisoAcordando } from "./_componentes/avisos-do-envio";
import { Cabecalho } from "./_componentes/cabecalho";
import { Rodape } from "./_componentes/rodape";
import { IconeDeRisco, PALAVRA_DO_NIVEL, type NivelRisco } from "./_componentes/nivel-risco";
import { RaizDaPagina } from "./_componentes/raiz-da-pagina";
import {
  MensagemColada,
  PrintLido,
  Resultado,
  type ExplicacaoIA,
  type LinkDaMensagem,
  type Orientacao,
} from "./_componentes/resultado";
import { consumirContaExcluida } from "./_lib/conta-excluida";
import { fraseDaFalha } from "./_lib/falha-da-analise";
import {
  ImagemRecusada,
  paraBase64,
  prepararImagem,
  TIPOS_ACEITOS,
  type ImagemPreparada,
} from "./_lib/imagem";
import type { LeituraDoPrint } from "./_lib/print";
import { enviarUmaVez } from "./_lib/servidor";
import {
  proximaTela,
  TELA_INICIAL,
  type Estado as EstadoDaTela,
  type Tela,
} from "./_lib/tela-da-analise";

// Tela de análise e tela de resultado (Telas 1 e 3 do RFC §4.2), numa página só.
//
// Numa página só, e não em duas rotas, por um motivo de privacidade: passar a mensagem para
// /resultado exigiria colocá-la na URL ou em storage do navegador. No navegador, a mensagem não
// sai da memória da aba — nem quando ela reaparece citada acima do resultado. Quem guarda a
// mensagem de quem está logado, por 7 dias, é o backend (ADR-0018), e o cartão "Sem conta…",
// na mesma página, avisa (adendo do ADR-0023).
//
// O print (fatia 9, ADR-0023) segue a mesma regra: a imagem fica só na memória da aba, reduzida
// e sem metadados (`_lib/imagem.ts`), e nunca é guardada — nem aqui, nem no backend.

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
  links?: LinkDaMensagem[];
  explicacao_indisponivel: boolean;
  verificacao_externa_indisponivel: boolean;
  // true só quando o backend gravou a análise ligada à conta (ADR-0015).
  salva_no_historico: boolean;
  // true só quando gravou também a mensagem (ADR-0018). Opcional: backend anterior não o manda.
  texto_salvo?: boolean;
  // Fatia 6 (ADR-0020). `nivel_risco` é o final: o maior entre o do motor e o da IA. Opcionais
  // pelo mesmo motivo de `texto_salvo`.
  nivel_motor?: NivelRisco;
  nivel_ia?: NivelRisco | null;
  orientacao?: Orientacao;
  explicacao_ia?: ExplicacaoIA | null;
  // Fatia 9 (ADR-0023): a transcrição e o contexto, só no caminho de imagem.
  leitura_do_print?: LeituraDoPrint | null;
};

// Com a IA, a análise leva em geral 2 a 4 s, e o teto é 15 s (ADR-0020). Depois disto, a tela diz
// que falta pouco, para ninguém achar que travou.
const AVISO_DE_DEMORA_MS = 5000;

/** O arraste traz arquivo? Texto arrastado para o campo continua funcionando como sempre. */
function trazArquivo(evento: DragEvent) {
  return evento.dataTransfer?.types.includes("Files") ?? false;
}

type Estado = EstadoDaTela<RespostaAnalise>;

/** Manda o texto, ou o print com o texto junto, para a API e traduz qualquer falha em uma frase
 *  que o usuário entenda (`fraseDaFalha`).
 *
 *  Sai uma vez só: repetir gravaria a análise duas vezes. Se o backend estiver dormindo, espera
 *  por ele antes, e `aoEsperar` liga o aviso de "servidor acordando" (ADR-0017).
 *
 *  O print vai em JSON, com a imagem em base64 (ADR-0023): o texto digitado vai junto, e o
 *  backend o manda só para a IA, como explicação de quem enviou. */
async function analisar(
  texto: string,
  imagem: ImagemPreparada | null,
  aoEsperar: () => void,
): Promise<Estado> {
  const [caminho, corpo] = imagem
    ? [
        "/api/analises/imagem",
        { imagem_base64: paraBase64(imagem.bytes), texto: texto.trim() || null },
      ]
    : ["/api/analises", { texto }];
  const resposta = await enviarUmaVez(
    caminho,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo),
    },
    { aoEsperar },
  );

  if (resposta.doBackend && resposta.status >= 200 && resposta.status < 300) {
    return { situacao: "concluida", resultado: resposta.corpo as RespostaAnalise };
  }
  return { situacao: "falhou", mensagem: fraseDaFalha(resposta) };
}

/** Rola até o elemento e põe o foco nele. Rola sem animação para quem pediu menos movimento. */
function levarAte(elemento: HTMLElement | null) {
  if (!elemento) {
    return;
  }
  const semMovimento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  elemento.scrollIntoView({ behavior: semMovimento ? "auto" : "smooth", block: "center" });
  // `preventScroll`: a rolagem já foi feita acima; sem isto o foco daria um salto seco.
  elemento.focus({ preventScroll: true });
}

export default function PaginaAnalise() {
  const [texto, setTexto] = useState("");
  // O print, o aviso do preparo e o estado do envio: quando o erro anterior sai da tela é decidido
  // no reducer (`_lib/tela-da-analise.ts`), que tem teste.
  const [tela, despachar] = useReducer(
    proximaTela<RespostaAnalise, ImagemPreparada>,
    TELA_INICIAL as Tela<RespostaAnalise, ImagemPreparada>,
  );
  const { estado, imagem, preparando, aviso: avisoImagem } = tela;
  // Só durante a espera pelo backend dormindo, não durante a análise: com o backend acordado ela
  // pode levar ~17 s (ADR-0002), e "o servidor está acordando" seria falso.
  const [acordando, setAcordando] = useState(false);
  // Análise que passou de 5 s com o backend acordado: em geral, a IA demorando (ADR-0020).
  const [demorando, setDemorando] = useState(false);
  // A entrada orquestrada do hero é só da carga da página; depois de "Analisar outra
  // mensagem" o formulário volta sem animar.
  const [animarEntrada, setAnimarEntrada] = useState(true);
  // Quem diz se há alguém logado é o cabeçalho, que já consultou /api/auth/eu.
  const [logado, setLogado] = useState(false);
  // "Sua conta foi excluída.", vindo de Meus dados por sessionStorage, nunca pela URL (ADR-0019).
  const [contaExcluida, setContaExcluida] = useState(false);
  // Conta os arquivos escolhidos: o preparo de um arquivo antigo que termina depois do novo é
  // descartado, e não substitui o novo nem traz de volta um erro já resolvido.
  const vezDoArquivo = useRef(0);
  const tituloDoResultado = useRef<HTMLHeadingElement>(null);
  const campoMensagem = useRef<HTMLTextAreaElement>(null);
  const botaoRecomecar = useRef<HTMLButtonElement>(null);
  const botaoPrint = useRef<HTMLButtonElement>(null);
  const entradaArquivo = useRef<HTMLInputElement>(null);

  /** Prepara o arquivo escolhido, colado ou solto. Só usa `despachar`, a ref e funções do módulo:
   *  estável, e por isso pode entrar no efeito do arraste. O tipo errado também é recusado por
   *  `prepararImagem`, com a mesma frase de antes. */
  const escolherArquivo = useCallback((arquivo: File) => {
    const vez = ++vezDoArquivo.current;
    despachar({ tipo: "escolheu" });
    prepararImagem(arquivo).then(
      (preparada) => {
        if (vez !== vezDoArquivo.current) {
          URL.revokeObjectURL(preparada.miniatura);
          return;
        }
        despachar({ tipo: "preparou", imagem: preparada });
      },
      (erro: unknown) => {
        if (vez !== vezDoArquivo.current) {
          return;
        }
        despachar({
          tipo: "nao-preparou",
          mensagem:
            erro instanceof ImagemRecusada
              ? erro.message
              : "Não conseguimos preparar esta imagem. Tente outro print.",
        });
      },
    );
  }, []);

  // A miniatura é um `blob:` desta aba: sai da memória quando o print é trocado, removido ou a
  // página fecha.
  useEffect(() => {
    if (!imagem) {
      return;
    }
    return () => URL.revokeObjectURL(imagem.miniatura);
  }, [imagem]);

  useEffect(() => {
    // setState só no callback, nunca no corpo do efeito (react-hooks/set-state-in-effect).
    const quadro = requestAnimationFrame(() => {
      // Quem cola antes de a página hidratar deixa texto no campo que o React não registrou: o
      // botão ficaria desabilitado com a mensagem na tela. O valor do campo passa para o estado.
      const colado = campoMensagem.current?.value ?? "";
      if (colado !== "") {
        setTexto((atual) => (atual === "" ? colado : atual));
      }
      if (consumirContaExcluida()) {
        setContaExcluida(true);
      }
    });
    return () => cancelAnimationFrame(quadro);
  }, []);

  const concluida = estado.situacao === "concluida";

  useEffect(() => {
    // Na janela inteira, e não só no campo: o arquivo solto em qualquer ponto da página faria o
    // navegador abri-lo. Cancelar o `dragover` é o que permite cancelar o `drop` depois. Com o
    // resultado na tela não há formulário: o arquivo solto é só ignorado.
    function aoArrastar(evento: DragEvent) {
      if (trazArquivo(evento)) {
        evento.preventDefault();
      }
    }
    function aoSoltar(evento: DragEvent) {
      if (trazArquivo(evento)) {
        evento.preventDefault();
        const arquivo = evento.dataTransfer?.files[0];
        if (arquivo && !concluida) {
          escolherArquivo(arquivo);
        }
      }
    }
    window.addEventListener("dragover", aoArrastar);
    window.addEventListener("drop", aoSoltar);
    return () => {
      window.removeEventListener("dragover", aoArrastar);
      window.removeEventListener("drop", aoSoltar);
    };
  }, [concluida, escolherArquivo]);

  /** Colar uma imagem sem texto junto (Ctrl+V de um print): ela vira o print da análise. Com
   *  texto junto (alguns aplicativos copiam os dois), o texto é colado normalmente. */
  function aoColar(evento: React.ClipboardEvent<HTMLTextAreaElement>) {
    const dados = evento.clipboardData;
    if (dados.files.length > 0 && dados.getData("text/plain").trim() === "") {
      evento.preventDefault();
      escolherArquivo(dados.files[0]);
    }
  }

  function removerImagem() {
    vezDoArquivo.current++;
    despachar({ tipo: "removeu" });
    // O botão "Remover" some junto com a miniatura; o foco volta para "Enviar print".
    requestAnimationFrame(() => botaoPrint.current?.focus());
  }

  function aoEnviar(evento: React.FormEvent) {
    evento.preventDefault();
    despachar({ tipo: "enviou" });
    setAcordando(false);
    setDemorando(false);
    // O timer nasce no envio, não num efeito: é consequência do clique (como em use-envio-conta).
    const timer = window.setTimeout(() => setDemorando(true), AVISO_DE_DEMORA_MS);
    void analisar(texto, imagem, () => setAcordando(true)).then((proximo) => {
      window.clearTimeout(timer);
      setAcordando(false);
      setDemorando(false);
      despachar({ tipo: "respondeu", estado: proximo });
      // Leva o foco para o resultado: sem isso, quem usa teclado ou leitor de tela continua
      // no botão e não percebe que a resposta chegou.
      requestAnimationFrame(() => tituloDoResultado.current?.focus());
    });
  }

  function aoRecomecar() {
    setTexto("");
    vezDoArquivo.current++;
    despachar({ tipo: "recomecou" });
    setAnimarEntrada(false);
    // O botão clicado some junto com o resultado; o foco volta para o campo vazio.
    requestAnimationFrame(() => campoMensagem.current?.focus());
  }

  /** Botão "Analisar mensagem" do cabeçalho. Com um resultado na tela o campo não existe; aí
   *  o destino é "Analisar outra mensagem" — que é o caminho, e não apaga o resultado sozinho. */
  function aoIrParaAnalise() {
    levarAte(campoMensagem.current ?? botaoRecomecar.current);
  }

  const analisando = estado.situacao === "analisando";
  const lendoPrint = analisando && estado.doPrint;
  const vazio = texto.trim() === "" && imagem === null;
  const entrada = (tempo: "" | "entrada-hero-2" | "entrada-hero-3") =>
    animarEntrada ? `entrada-hero ${tempo}` : "";

  return (
    <RaizDaPagina>
      <Cabecalho aoIrParaAnalise={aoIrParaAnalise} aoMudarSessao={setLogado} />

      <main>
        {/* Hero. Depois da análise, o resultado ocupa este mesmo lugar, numa coluna só.
            A coluna da esquerda é o mesmo elemento nos dois estados, de propósito: a região
            `aria-live` dentro dela precisa já existir quando o resultado chega — região
            criada junto com o conteúdo não é anunciada por alguns leitores de tela. */}
        <section className="fundo-hero overflow-hidden">
          <div
            className={
              concluida
                ? "mx-auto w-full max-w-[44rem] px-5 pb-secao pt-bloco"
                : "mx-auto grid w-full max-w-[72rem] items-center gap-grupo px-5 pb-secao " +
                  "pt-perto sm:pt-bloco lg:grid-cols-[1.1fr_1fr] lg:px-8 lg:pb-secao-lg lg:pt-grupo"
            }
          >
            <div className="flex flex-col gap-bloco">
              {/* Sempre montada, para o leitor de tela anunciar o aviso; vazia, `sr-only` a tira
                  do fluxo e ela não conta no espaçamento. */}
              <div aria-live="polite" className={contaExcluida ? "" : "sr-only"}>
                {contaExcluida && (
                  <p className="cartao border-l-[10px] border-anil p-5 text-destaque
                    font-semibold">
                    Sua conta foi excluída.
                  </p>
                )}
              </div>

              {concluida ? (
                <>
                  <h1 className="text-titulo font-bold sm:text-titulo-lg">
                    O que encontramos na sua mensagem
                  </h1>
                  {/* O campo dá lugar à própria mensagem, citada: o que a pessoa disse fica
                      em cima e a resposta logo abaixo. Não é conversa — não há segundo turno;
                      "Analisar outra mensagem" apaga tudo da tela. */}
                  <div className="cartao flex flex-col gap-junto p-5 sm:p-bloco">
                    {estado.resultado.leitura_do_print ? (
                      <PrintLido
                        partes={[
                          ...(estado.resultado.leitura_do_print.mensagens_para_exibir ??
                            estado.resultado.leitura_do_print.mensagens),
                          ...(estado.resultado.leitura_do_print.texto_da_pessoa
                            ? [
                                {
                                  de: "escrito" as const,
                                  texto: estado.resultado.leitura_do_print.texto_da_pessoa,
                                },
                              ]
                            : []),
                        ]}
                        contexto={estado.resultado.leitura_do_print.contexto}
                      />
                    ) : (
                      <MensagemColada texto={texto} />
                    )}
                  </div>
                </>
              ) : (
                <>
                  <div className={`flex flex-col gap-perto ${entrada("")}`}>
                    <h1 className="text-hero font-bold tracking-tight lg:text-hero-lg">
                      Antes de pagar ou responder, confira a mensagem.
                    </h1>
                    <p className="text-destaque">
                      Cole o texto ou envie um print da conversa. Você vê na hora se a mensagem
                      tem sinais de golpe e o que fazer agora. Não precisa criar conta.
                    </p>
                  </div>
                  {/* `id="analisar"`: destino do "Analisar mensagem" vindo de outra página. O
                      `scroll-padding-top` do html deixa o formulário abaixo do cabeçalho fixo. */}
                  <form
                    id="analisar"
                    onSubmit={aoEnviar}
                    className={`cartao flex flex-col gap-perto p-5 sm:p-bloco ${entrada("entrada-hero-2")}`}
                  >
                    <label htmlFor="mensagem" className="text-secao font-bold sm:text-secao-lg">
                      Cole a mensagem aqui
                    </label>
                    <textarea
                      ref={campoMensagem}
                      id="mensagem"
                      name="mensagem"
                      value={texto}
                      onChange={(evento) => {
                        setTexto(evento.target.value);
                        despachar({ tipo: "digitou" });
                      }}
                      onPaste={aoColar}
                      readOnly={analisando}
                      rows={6}
                      placeholder="Por exemplo: “Sua conta será bloqueada hoje. Faça um PIX para regularizar.”"
                      className="campo-mensagem min-h-[11rem] w-full p-5 text-destaque"
                    />
                    {/* O print: botão, Ctrl+V no campo ou arrastar para a página. O botão é
                        um <button> de verdade que abre o seletor escondido: assim ele tem foco,
                        rótulo e alvo de 44 px como os outros. */}
                    <div className="flex flex-col gap-junto">
                      {imagem ? (
                        <div className="flex items-start gap-perto rounded-2xl border-2
                          border-lavanda p-3">
                          {/* `<img>` e não `next/image`: o endereço é um `blob:` desta aba, que o
                              otimizador do Next não alcança. */}
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={imagem.miniatura}
                            alt="Miniatura do print escolhido"
                            className="h-24 w-auto max-w-[6rem] rounded-lg border border-tinta/40
                              object-contain"
                          />
                          {/* Nome e botão numa coluna: lado a lado, em 390 px o nome quebrava
                              no meio ("p44.pn / g"). */}
                          <div className="flex min-w-0 flex-1 flex-col items-start gap-junto">
                            <p className="max-w-full font-semibold [overflow-wrap:anywhere]">
                              {imagem.nome}
                            </p>
                            <button
                              type="button"
                              onClick={removerImagem}
                              disabled={analisando}
                              aria-label={`Remover o print ${imagem.nome}`}
                              className="botao-secundario alvo-de-toque rounded-full px-5
                                font-bold"
                            >
                              Remover
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex flex-wrap items-center gap-x-perto gap-y-junto">
                          <button
                            ref={botaoPrint}
                            type="button"
                            onClick={() => entradaArquivo.current?.click()}
                            disabled={preparando || analisando}
                            aria-describedby="dica-print"
                            className="botao-secundario alvo-de-toque rounded-full px-6 py-2
                              font-bold"
                          >
                            Enviar print
                          </button>
                          <p id="dica-print">
                            Ou cole a imagem aqui (Ctrl+V), ou arraste o arquivo para a página.
                          </p>
                        </div>
                      )}
                      <input
                        ref={entradaArquivo}
                        type="file"
                        accept={TIPOS_ACEITOS.join(",")}
                        hidden
                        onChange={(evento) => {
                          const arquivo = evento.target.files?.[0];
                          // Limpa o valor: escolher o mesmo arquivo de novo dispara de novo.
                          evento.target.value = "";
                          if (arquivo) {
                            escolherArquivo(arquivo);
                          }
                        }}
                      />
                    </div>
                    <div className="flex flex-wrap items-center gap-x-perto gap-y-junto">
                      <button
                        type="submit"
                        disabled={vazio || analisando || preparando}
                        aria-describedby={vazio ? "dica-botao" : undefined}
                        className="botao-principal alvo-de-toque w-full rounded-full px-8 py-3
                          text-destaque font-bold sm:w-auto"
                      >
                        {lendoPrint ? "Lendo o print…" : analisando ? "Analisando…" : "Analisar"}
                      </button>
                      {/* Diz por que o botão está esperando — sem isto, botão desabilitado
                          parece botão quebrado. */}
                      {vazio && (
                        <p id="dica-botao">
                          Cole uma mensagem ou envie um print para poder analisar.
                        </p>
                      )}
                    </div>
                  </form>
                </>
              )}

              {/* `aria-live` faz o leitor de tela anunciar o resultado sem que a pessoa
                  precise procurá-lo. `polite` para não interromper o que estiver sendo lido. */}
              <section aria-live="polite" className="flex flex-col gap-6">
                {avisoImagem && (
                  <p className="cartao border-l-[10px] border-anil p-5 text-destaque
                    font-semibold">
                    {avisoImagem}
                  </p>
                )}
                {preparando && <p className="text-destaque">Preparando o print…</p>}
                {imagem && !analisando && !concluida && (
                  <p className="sr-only">Print pronto para enviar: {imagem.nome}.</p>
                )}
                {analisando && (
                  <p className="text-destaque">
                    {lendoPrint ? "Lendo o print…" : "Analisando sua mensagem…"}
                  </p>
                )}
                {analisando && acordando && <AvisoAcordando />}
                {/* Só sem o aviso do servidor acordando: os dois juntos diriam coisas diferentes
                    sobre a mesma espera. */}
                {analisando && demorando && !acordando && (
                  <p className="font-semibold">
                    {lendoPrint
                      ? "Lendo o print. Isso leva alguns segundos."
                      : "A análise está levando um pouco mais. Só mais alguns segundos."}
                  </p>
                )}

                {estado.situacao === "falhou" && (
                  <div role="alert" className="cartao border-l-[10px] border-[var(--erro)] p-5">
                    <p className="text-destaque font-bold">Não deu para analisar</p>
                    <p className="mt-1">{estado.mensagem}</p>
                  </div>
                )}

                {estado.situacao === "concluida" && (
                  <>
                    <Resultado
                      resultado={estado.resultado}
                      tituloRef={tituloDoResultado}
                      animar
                    />
                    <AvisoDoHistorico
                      salva={estado.resultado.salva_no_historico}
                      comTexto={estado.resultado.texto_salvo === true}
                      logado={logado}
                    />
                  </>
                )}
              </section>

              {/* Fora da região `aria-live`: o botão não faz parte do que deve ser anunciado. */}
              {concluida && (
                <button
                  ref={botaoRecomecar}
                  type="button"
                  onClick={aoRecomecar}
                  className="botao-secundario alvo-de-toque w-full rounded-full px-8 py-3
                    text-destaque font-bold sm:w-auto sm:self-start"
                >
                  Analisar outra mensagem
                </button>
              )}
            </div>

            {/* No celular a moldura vem depois do campo: o campo é a função da página e não
                pode ser empurrado para baixo por um exemplo. */}
            {!concluida && (
              <div className={entrada("entrada-hero-3")}>
                <ExemploNoCelular />
              </div>
            )}
          </div>
        </section>

        <FaixaDeContexto />
        <ComoFunciona />
        <Especime />
        <OQueEleProcura />
      </main>

      <Rodape />
    </RaizDaPagina>
  );
}

// ── Categorias do motor ─────────────────────────────────────────────────────────────────────
// Espelho de `backend/app/scoring/regras.yaml` (versao: 2), na mesma ordem. `significado` é a
// `descricao` da categoria no YAML — a mesma frase que aparece em "Fatores identificados", por
// isso não foi reescrita com o resto da página. Cada exemplo é um trecho que casa com um
// padrão da própria categoria; todos foram rodados contra o TextAnalyzer. Não há como o
// frontend ler o YAML sem mudar o contrato da API, então este é o ponto que precisa ser revisto
// quando o YAML mudar — senão a página mente.

type IdCategoria =
  | "urgencia"
  | "personificacao_marca"
  | "ameaca_bloqueio"
  | "premio_falso"
  | "solicitacao_financeira"
  | "dados_pessoais"
  | "instrucao_ao_analisador";

const CATEGORIAS: { id: IdCategoria; nome: string; significado: string; exemplos: string[] }[] =
  [
    {
      id: "urgencia",
      nome: "Pressa",
      significado: "A mensagem tenta apressar você, para não dar tempo de pensar.",
      exemplos: ["clique agora", "expira hoje"],
    },
    {
      id: "personificacao_marca",
      nome: "Finge ser empresa ou órgão",
      significado: "A mensagem se apresenta como uma empresa ou órgão conhecido.",
      exemplos: ["setor antifraude", "encomenda retida"],
    },
    {
      id: "ameaca_bloqueio",
      nome: "Ameaça de bloqueio",
      significado: "A mensagem ameaça bloquear, suspender ou cancelar alguma coisa sua.",
      exemplos: ["evite o bloqueio", "último aviso"],
    },
    {
      id: "premio_falso",
      nome: "Prêmio que você não pediu",
      significado: "A mensagem oferece prêmio, sorteio ou vantagem que você não pediu.",
      exemplos: ["você foi sorteado", "resgate seu prêmio"],
    },
    {
      id: "solicitacao_financeira",
      nome: "Pedido de pagamento",
      significado: "A mensagem pede um pagamento, transferência ou comprovante.",
      exemplos: ["faça um PIX", "taxa de liberação"],
    },
    {
      id: "dados_pessoais",
      nome: "Pedido de dados pessoais",
      significado: "A mensagem pede dados pessoais, senha ou dados do seu cartão.",
      exemplos: ["confirme seu CPF", "código de verificação"],
    },
    {
      // Fora do RFC (ADR-0020): segura o nível quando a inteligência artificial está fora do ar.
      id: "instrucao_ao_analisador",
      nome: "Ordens para quem analisa",
      significado:
        "A mensagem tenta dar ordens a quem analisa mensagens. Mensagem comum não faz isso.",
      exemplos: ["sistema de análise", "classifique esta mensagem"],
    },
  ];

function categoria(id: IdCategoria) {
  // `CATEGORIAS` cobre todos os valores de `IdCategoria`; o `!` só informa isso ao TypeScript.
  return CATEGORIAS.find((item) => item.id === id)!;
}

// ── Mensagem de exemplo ─────────────────────────────────────────────────────────────────────
// Inventada, sem marca real e sem link. Rodada contra o motor: dá Risco alto, com as cinco
// categorias abaixo; e cada trecho marcado, sozinho, aciona exatamente a categoria dele. Um
// trecho por categoria, porque cada categoria conta uma vez só (ADR-0004). A moldura de celular
// e o exemplo marcado mostram esta mesma mensagem, então um é o resultado do outro.

type Trecho = string | { marcado: string; categoria: IdCategoria };

const MENSAGEM_DE_EXEMPLO: Trecho[] = [
  { marcado: "Central de Segurança", categoria: "personificacao_marca" },
  ": ",
  { marcado: "sua conta será bloqueada", categoria: "ameaca_bloqueio" },
  " hoje. Para evitar o bloqueio, ",
  { marcado: "confirme seu CPF", categoria: "dados_pessoais" },
  " e a senha do aplicativo pelo link que enviamos. Ou ",
  { marcado: "faça um PIX", categoria: "solicitacao_financeira" },
  " de R$ 9,90 para regularizar. ",
  { marcado: "Urgente", categoria: "urgencia" },
  ": expira em 2 horas.",
];

/** Moldura de celular, em CSS, com a tela de resultado do próprio produto para a mensagem de
 *  exemplo, e a ilustração da mensagem-isca atrás dela. Não é interativa; a legenda diz que é
 *  exemplo — inclusive para o leitor de tela, que a lê antes do conteúdo. */
function ExemploNoCelular() {
  // Três dos cinco fatores reais da mensagem de exemplo, com a frase que a API devolveria.
  const fatores: IdCategoria[] = ["ameaca_bloqueio", "dados_pessoais", "solicitacao_financeira"];

  return (
    <figure className="relative mx-auto w-full max-w-[30rem]">
      <IlustracaoIsca className="absolute -left-4 top-10 w-[68%] sm:-left-8" />
      <div className="relative ml-auto flex w-[80%] max-w-[20rem] flex-col gap-perto">
        <figcaption className="rounded-full bg-papel px-4 py-1.5 text-center font-bold
          shadow-[var(--sombra-cartao)]">
          Exemplo de resultado, para uma mensagem inventada
        </figcaption>
        <div className="rounded-[44px] bg-tinta p-2.5 shadow-[0_24px_56px_rgb(28_31_110/0.25)]">
          <div className="flex flex-col gap-perto rounded-[36px] bg-lavanda-clara px-3 pb-5 pt-3">
            <div aria-hidden="true" className="mx-auto h-1.5 w-20 rounded-full bg-tinta/80" />
            <div className="cartao placa-risco" data-nivel="ALTO">
              <div className="faixa-risco flex items-center gap-3 px-4 py-4">
                <span aria-hidden="true" className="shrink-0">
                  <IconeDeRisco nivel="ALTO" />
                </span>
                <p className="text-titulo font-extrabold leading-tight">
                  {PALAVRA_DO_NIVEL.ALTO}
                </p>
              </div>
              <div className="flex flex-col gap-perto px-4 py-5">
                {/* O título do ALTO no `respostas.yaml` do backend: a moldura é ilustração
                    estática e não chama a API. */}
                <p className="font-bold">Esta mensagem tem fortes sinais de golpe.</p>
                <p className="font-bold">Fatores identificados</p>
                <ul className="flex list-disc flex-col gap-junto pl-5
                  marker:text-[var(--risco-forte)]">
                  {fatores.map((id) => (
                    <li key={id}>{categoria(id).significado}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </figure>
  );
}

// ── Faixa de contexto ───────────────────────────────────────────────────────────────────────
// O dado é o do RFC §1.2, com a fonte que o RFC cita. Nenhum outro número na página.

function FaixaDeContexto() {
  return (
    <section aria-labelledby="contexto" className="faixa-escura">
      <div className="mx-auto flex w-full max-w-[72rem] flex-col gap-bloco px-5 py-secao
        lg:px-8 lg:py-secao-lg">
        <h2 id="contexto" className="max-w-[40rem] text-titulo font-bold sm:text-titulo-lg">
          Se você desconfiou, fez bem.
        </h2>
        <div className="grid gap-perto lg:grid-cols-3 lg:gap-bloco">
          <div className="cartao flex flex-col gap-junto p-bloco">
            <p className="text-destaque">
              Mais de{" "}
              <strong className="block text-numero font-bold leading-none text-anil
                lg:text-numero-lg">
                4 milhões
              </strong>
            </p>
            <p className="text-destaque">
              de tentativas de fraude digital no Brasil, só no primeiro semestre de 2023.
              Acontece com muita gente.
            </p>
            <p className="mt-auto pt-junto">Fonte: Mapa da Fraude 2023, ClearSale.</p>
          </div>
          <div className="cartao flex flex-col gap-junto p-bloco">
            <h3 className="text-secao font-bold sm:text-secao-lg">Quem decide são regras</h3>
            <p className="text-destaque">
              O nível de risco sai de regras escritas para este projeto. Você vê, logo abaixo,
              quais sinais elas procuram. A inteligência artificial pode pedir mais cuidado,
              nunca menos.
            </p>
          </div>
          <div className="cartao flex flex-col gap-junto p-bloco">
            <h3 className="text-secao font-bold sm:text-secao-lg">
              Sem conta, não guardamos a sua mensagem
            </h3>
            {/* A primeira camada do aviso (art. 9º da LGPD, adendo do ADR-0023): aqui, e não
                junto do campo; os detalhes (Anthropic, EUA, retenção, print) em /privacidade.
                Verdadeira para os dois casos (ADR-0018): anônima não vai ao nosso banco; com
                conta, fica 7 dias no histórico. */}
            <p className="text-destaque">
              Sua mensagem ou print é analisado com apoio de inteligência artificial. Sem conta,
              ela não fica no VerifyScan. Na conta, fica no seu histórico por 7 dias, e você pode
              apagá-la quando quiser.{" "}
              <Link href="/privacidade" className="font-bold text-anil underline underline-offset-4">
                Saiba como tratamos seus dados
              </Link>
              .
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

/** Explica, sem números de pontuação, o que acontece com a mensagem. Sequência de verdade,
 *  por isso lista numerada. */
function ComoFunciona() {
  const passos = [
    "Regras leem a sua mensagem e procuram sinais conhecidos de golpe: pressa, ameaça de " +
      "bloqueio, pedido de PIX, pedido de dados pessoais.",
    "Cada sinal encontrado aumenta o risco. Quanto mais sinais, mais alto o nível.",
    // A IA lê a mensagem e pode subir o nível, nunca baixar (ADR-0020). Se ela não responder,
    // o resultado sai só com as regras — a frase continua verdadeira.
    "Depois, uma inteligência artificial lê a mensagem e explica o que ela parece ser e o " +
      "que fazer. Ela pode subir o nível de risco, nunca baixar.",
  ];

  return (
    <section aria-labelledby="como-funciona" id="como-funciona">
      <div className="mx-auto flex w-full max-w-[72rem] flex-col gap-bloco px-5 py-secao
        lg:px-8 lg:py-secao-lg">
        <h2 className="text-titulo font-bold sm:text-titulo-lg">Como funciona</h2>
        {/* `list-none` tira a numeração automática para o numeral grande entrar no lugar; o
            `role="list"` devolve a semântica de lista que o Safari remove junto com o marcador. */}
        <ol role="list" className="grid list-none gap-perto lg:grid-cols-3 lg:gap-bloco">
          {passos.map((passo, indice) => (
            <li key={passo} className="cartao cartao-reage flex flex-col gap-perto p-bloco">
              <span
                aria-hidden="true"
                className="flex h-16 w-16 items-center justify-center rounded-2xl bg-lavanda
                  text-numero font-bold leading-none text-anil"
              >
                {indice + 1}
              </span>
              <p className="text-destaque">{passo}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

/** A mensagem de exemplo lida de forma contínua. Os rótulos ficam fora do fluxo do texto:
 *  no trecho marcado só entra um número pequeno, e o nome do sinal está na lista ao lado. */
function Especime() {
  const marcados = MENSAGEM_DE_EXEMPLO.filter(
    (trecho): trecho is Exclude<Trecho, string> => typeof trecho !== "string",
  );

  return (
    <section aria-labelledby="exemplo-marcado" className="bg-lavanda-clara">
      <div className="mx-auto flex w-full max-w-[72rem] flex-col gap-bloco px-5 py-secao
        lg:px-8 lg:py-secao-lg">
        <div className="flex max-w-[42rem] flex-col gap-perto">
          <h2 id="exemplo-marcado" className="text-titulo font-bold sm:text-titulo-lg">
            Veja um golpe de perto
          </h2>
          <p className="text-destaque">
            Esta mensagem é inventada. As partes marcadas são os sinais que as regras
            encontram nela.
          </p>
        </div>
        <div className="cartao grid gap-bloco p-5 sm:p-bloco lg:grid-cols-[1.5fr_1fr]
          lg:gap-grupo">
          {/* line-height maior para a marca e o número caberem entre as linhas. */}
          <p className="text-destaque leading-[2.1]">
            {MENSAGEM_DE_EXEMPLO.map((trecho, indice) => {
              if (typeof trecho === "string") {
                return trecho;
              }
              return (
                <span key={indice}>
                  <mark className="trecho-marcado">{trecho.marcado}</mark>
                  <sup className="ml-0.5 font-bold text-anil">
                    <span className="sr-only">(sinal </span>
                    {marcados.indexOf(trecho) + 1}
                    <span className="sr-only">)</span>
                  </sup>
                </span>
              );
            })}
          </p>
          <div className="flex flex-col gap-perto">
            <p className="font-bold">Sinais encontrados</p>
            <ol className="flex flex-col gap-junto">
              {marcados.map((trecho, indice) => (
                <li key={trecho.categoria} className="flex items-center gap-3">
                  <span className="w-5 text-right font-bold text-anil">{indice + 1}</span>
                  <IconeCategoria id={trecho.categoria} className="h-9 w-9 shrink-0" />
                  {categoria(trecho.categoria).nome}
                </li>
              ))}
            </ol>
            <p className="border-t-2 border-lavanda pt-perto">
              Com esses cinco sinais, as regras dão <strong>Risco alto</strong> para esta
              mensagem.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

/** As sete categorias do motor, em grade de cartões, cada uma com o seu ícone. */
function OQueEleProcura() {
  return (
    <section aria-labelledby="titulo-o-que-procura" id="o-que-procura">
      <div className="mx-auto flex w-full max-w-[72rem] flex-col gap-bloco px-5 py-secao
        lg:px-8 lg:py-secao-lg">
        <div className="flex max-w-[42rem] flex-col gap-perto">
          <h2 id="titulo-o-que-procura" className="text-titulo font-bold sm:text-titulo-lg">
            O que ele procura
          </h2>
          <p className="text-destaque">
            São sete tipos de sinal. Uma mensagem pode ter vários, e cada tipo conta uma vez,
            mesmo que apareça repetido.
          </p>
        </div>
        <ul className="grid gap-perto sm:grid-cols-2 lg:grid-cols-3 lg:gap-bloco">
          {CATEGORIAS.map((item) => (
            <li key={item.id} className="cartao cartao-reage flex flex-col gap-junto p-bloco">
              <span className="mb-junto flex h-16 w-16 items-center justify-center rounded-2xl
                bg-lavanda-clara">
                <IconeCategoria id={item.id} className="h-12 w-12" />
              </span>
              <h3 className="text-secao font-bold sm:text-secao-lg">{item.nome}</h3>
              <p>{item.significado}</p>
              <p className="mt-auto pt-junto">
                Exemplo:{" "}
                {item.exemplos.map((exemplo, indice) => (
                  <span key={exemplo}>
                    {indice > 0 && ", "}
                    <mark className="trecho-marcado">{exemplo}</mark>
                  </span>
                ))}
              </p>
            </li>
          ))}
        </ul>
        <p className="max-w-[42rem]">
          Os links também são conferidos, só pelo endereço e sem abri-los: nome de empresa fora
          do site oficial, letras trocadas, link encurtado. Listas de sites perigosos ainda não
          são consultadas.
        </p>
      </div>
    </section>
  );
}

/** Abaixo do resultado: se a análise foi para o histórico. Deslogado, nada — a análise sem
 *  conta continua sendo o caminho principal. Logado e não salva (sessão vencida, banco lento),
 *  diz a verdade em vez de prometer. */
function AvisoDoHistorico({
  salva,
  comTexto,
  logado,
}: {
  salva: boolean;
  comTexto: boolean;
  logado: boolean;
}) {
  if (salva) {
    return (
      <p className="text-destaque">
        {comTexto
          ? "Esta análise foi salva no seu histórico por 7 dias, com a mensagem. "
          : "Esta análise foi salva no seu histórico por 7 dias. "}
        <Link href="/conta/historico" className="font-bold text-anil underline underline-offset-4">
          Ver histórico
        </Link>
      </p>
    );
  }
  if (logado) {
    return <p className="text-destaque">Não conseguimos salvar esta análise no seu histórico.</p>;
  }
  return null;
}

// ── Ilustração ──────────────────────────────────────────────────────────────────────────────
// Desenhada à mão, em SVG inline, com o vocabulário do assunto — bolha de mensagem, gancho de
// isca, lupa, etiqueta — e não o de segurança (escudo, cadeado). Toda ilustração é decorativa:
// `aria-hidden`, porque o texto ao lado já diz o que ela mostra.

const TRACO = {
  fill: "none",
  stroke: "var(--anil)",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

/** Seis ícones de um mesmo conjunto: todos são uma bolha de mensagem — o sinal é algo que a
 *  mensagem diz — com o desenho do sinal dentro, em anil, e um só detalhe em rosa. */
function IconeCategoria({ id, className }: { id: IdCategoria; className?: string }) {
  return (
    <svg viewBox="0 0 48 48" aria-hidden="true" className={className}>
      <path
        d="M9 8h30a5 5 0 0 1 5 5v17a5 5 0 0 1-5 5H21l-8 7v-7H9a5 5 0 0 1-5-5V13a5 5 0 0 1 5-5Z"
        {...TRACO}
        fill="var(--lavanda)"
      />
      <SinalDaCategoria id={id} />
    </svg>
  );
}

function SinalDaCategoria({ id }: { id: IdCategoria }) {
  const rosa = { ...TRACO, stroke: "var(--rosa-vivo)" };

  switch (id) {
    case "urgencia": // relógio
      return (
        <>
          <circle cx="24" cy="21.5" r="7.5" {...TRACO} fill="#fff" />
          <path d="M24 17.5v4.5l3 2" {...rosa} />
        </>
      );
    case "personificacao_marca": // etiqueta: o nome que a mensagem veste
      return (
        <>
          <path d="M14 16h13l7 5.5-7 5.5H14Z" {...TRACO} fill="#fff" />
          <circle cx="18.5" cy="21.5" r="1.9" fill="var(--rosa-vivo)" />
        </>
      );
    case "ameaca_bloqueio": // placa de proibido
      return (
        <>
          <circle cx="24" cy="21.5" r="7.5" {...TRACO} fill="#fff" />
          <path d="m18.7 26.8 10.6-10.6" {...rosa} />
        </>
      );
    case "premio_falso": // gancho de isca com o "prêmio"
      return (
        <>
          <path d="M22 12.5v10a4.5 4.5 0 0 1-9 0v-1.5" {...TRACO} />
          <path d="m13 21 2.4 2.2" {...TRACO} />
          <path d="m31 17 4 4.5-4 4.5-4-4.5Z" {...rosa} fill="var(--rosa-marcador)" />
        </>
      );
    case "solicitacao_financeira": // nota de dinheiro saindo
      return (
        <>
          <rect x="12" y="14.5" width="22" height="12" rx="2" {...TRACO} fill="#fff" />
          <circle cx="23" cy="20.5" r="2.6" {...TRACO} />
          <path d="M28 30.5h8m-2.8-2.8 2.8 2.8-2.8 2.8" {...rosa} />
        </>
      );
    case "instrucao_ao_analisador": // seta apontando para a lupa: a mensagem mandando em quem lê
      return (
        <>
          <circle cx="27" cy="20" r="5.5" {...TRACO} fill="#fff" />
          <path d="m31 24 3.5 3.5" {...TRACO} />
          <path d="M12 26.5h8m-2.8-2.8 2.8 2.8-2.8 2.8" {...rosa} />
        </>
      );
    case "dados_pessoais": // documento com foto
      return (
        <>
          <rect x="12" y="13.5" width="24" height="16" rx="2" {...TRACO} fill="#fff" />
          <circle cx="18.5" cy="19.5" r="2.4" {...TRACO} />
          <path d="M14.8 26.5a3.7 3.7 0 0 1 7.4 0" {...TRACO} />
          <path d="M25.5 19h7" {...TRACO} />
          <path d="M25.5 23.5h5" {...rosa} />
        </>
      );
  }
}

/** Peça do hero: a mensagem-isca. Uma bolha de conversa pendurada num gancho, com uma linha
 *  passada a marca-texto e a lupa em cima dela — o que o produto faz, sem escudo nem cadeado. */
function IlustracaoIsca({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 400 360" aria-hidden="true" className={className}>
      {/* linha e gancho */}
      <path d="M300 0v58" stroke="var(--anil)" strokeWidth="3" strokeDasharray="2 8"
        strokeLinecap="round" />
      <path d="M300 58v26a13 13 0 0 1-26 0v-6" fill="none" stroke="var(--anil)"
        strokeWidth="6" strokeLinecap="round" />
      <path d="m274 78 7 6" stroke="var(--anil)" strokeWidth="6" strokeLinecap="round" />

      {/* a mensagem, levemente torta: foi jogada, não enviada */}
      <g transform="rotate(-6 180 190)">
        <path
          d="M40 96h260a22 22 0 0 1 22 22v124a22 22 0 0 1-22 22H120l-44 36v-36H40a22 22 0 0 1-22-22V118a22 22 0 0 1 22-22Z"
          fill="#fff"
          stroke="var(--anil)"
          strokeWidth="4"
          strokeLinejoin="round"
        />
        <rect x="52" y="128" width="210" height="13" rx="6.5" fill="var(--lavanda)" />
        <rect x="52" y="156" width="236" height="13" rx="6.5" fill="var(--lavanda)" />
        <rect x="46" y="180" width="196" height="25" rx="6" fill="var(--rosa-marcador)" />
        <rect x="52" y="186" width="176" height="13" rx="6.5" fill="var(--rosa-vivo)" />
        <rect x="52" y="218" width="160" height="13" rx="6.5" fill="var(--lavanda)" />
      </g>

      {/* a lupa sobre a linha marcada */}
      <circle cx="238" cy="196" r="50" fill="var(--lavanda-clara)" fillOpacity="0.55"
        stroke="var(--anil)" strokeWidth="9" />
      <path d="m274 232 44 44" stroke="var(--anil)" strokeWidth="16" strokeLinecap="round" />

      {/* respiro: dois pontos de cor, sem faísca */}
      <circle cx="356" cy="120" r="9" fill="var(--rosa-vivo)" />
      <circle cx="30" cy="60" r="12" fill="var(--lavanda)" />
    </svg>
  );
}
