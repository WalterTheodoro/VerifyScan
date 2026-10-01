"use client";

import { useRef, useState } from "react";

import { Cabecalho } from "./_componentes/cabecalho";
import { Rodape } from "./_componentes/rodape";
import { RaizDaPagina } from "./_componentes/raiz-da-pagina";

// Tela de análise e tela de resultado (Telas 1 e 3 do RFC §4.2), numa página só.
//
// Numa página só, e não em duas rotas, por um motivo de privacidade: passar a mensagem para
// /resultado exigiria colocá-la na URL ou em storage do navegador. A mensagem do usuário não
// sai da memória da aba — nem quando ela reaparece citada acima do resultado.

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

/** Texto exibido para cada nível. Nunca só a cor: a palavra e o ícone carregam o sentido.
 *  O tom acalma sem minimizar: quem lê isto pode estar com medo de já ter perdido dinheiro. */
const APRESENTACAO: Record<
  NivelRisco,
  { palavra: string; resumo: string; recomendacao: string }
> = {
  BAIXO: {
    palavra: "Risco baixo",
    // A segunda frase é obrigatória: hoje só o texto é analisado (sem conferir o site do
    // link, sem ler imagem, sem consulta externa), então risco baixo quer dizer "não achei
    // sinais conhecidos", nunca "é seguro".
    resumo:
      "Não encontramos sinais conhecidos de golpe nesta mensagem. Isso não é garantia de " +
      "que ela seja segura: por enquanto, lemos só o texto — ainda não conferimos o site do " +
      "link, não lemos imagens e não consultamos listas de sites perigosos. Se algo parecer " +
      "estranho, confie na sua desconfiança.",
    recomendacao:
      "Mesmo assim, se ela pedir dinheiro ou dados, confirme com a empresa pelo telefone ou " +
      "aplicativo oficial antes de responder.",
  },
  MEDIO: {
    palavra: "Risco médio",
    resumo: "Esta mensagem tem sinais que pedem cuidado.",
    recomendacao:
      "Por enquanto, não clique em links e não passe seus dados. Confirme com a empresa, " +
      "pelo telefone ou aplicativo oficial, se a mensagem é verdadeira.",
  },
  ALTO: {
    palavra: "Risco alto",
    resumo: "Esta mensagem tem sinais fortes de golpe. Você fez bem em conferir antes.",
    recomendacao:
      "Não clique no link, não pague nada e não passe seus dados. Apague a mensagem e " +
      "bloqueie quem enviou. Se já pagou ou passou algum dado, ligue para o seu banco pelo " +
      "número que está no verso do cartão.",
  },
};

/** Manda o texto para a API e traduz qualquer falha em uma frase que o usuário entenda. */
async function analisar(texto: string): Promise<Estado> {
  try {
    const resposta = await fetch("/api/analises", {
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
  const [estado, setEstado] = useState<Estado>({ situacao: "pronta" });
  // A entrada orquestrada do hero é só da carga da página; depois de "Analisar outra
  // mensagem" o formulário volta sem animar.
  const [animarEntrada, setAnimarEntrada] = useState(true);
  const tituloDoResultado = useRef<HTMLHeadingElement>(null);
  const campoMensagem = useRef<HTMLTextAreaElement>(null);
  const botaoRecomecar = useRef<HTMLButtonElement>(null);

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
    setAnimarEntrada(false);
    // O botão clicado some junto com o resultado; o foco volta para o campo vazio.
    requestAnimationFrame(() => campoMensagem.current?.focus());
  }

  /** Botão "Analisar mensagem" do cabeçalho. Com um resultado na tela o campo não existe; aí
   *  o destino é "Analisar outra mensagem" — que é o caminho, e não apaga o resultado sozinho. */
  function aoIrParaAnalise() {
    levarAte(campoMensagem.current ?? botaoRecomecar.current);
  }

  const concluida = estado.situacao === "concluida";
  const vazio = texto.trim() === "";
  const entrada = (tempo: "" | "entrada-hero-2" | "entrada-hero-3") =>
    animarEntrada ? `entrada-hero ${tempo}` : "";

  return (
    <RaizDaPagina>
      <Cabecalho aoIrParaAnalise={aoIrParaAnalise} />

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
              {concluida ? (
                <>
                  <h1 className="text-titulo font-bold sm:text-titulo-lg">
                    O que encontramos na sua mensagem
                  </h1>
                  {/* O campo dá lugar à própria mensagem, citada: o que a pessoa disse fica
                      em cima e a resposta logo abaixo. Não é conversa — não há histórico nem
                      segundo turno; "Analisar outra mensagem" apaga tudo. */}
                  <div className="cartao flex flex-col gap-junto p-5 sm:p-bloco">
                    <p className="font-bold">Você colou:</p>
                    <blockquote
                      className="whitespace-pre-wrap break-words border-l-4 border-anil py-1
                        pl-5 text-destaque"
                    >
                      {texto}
                    </blockquote>
                  </div>
                </>
              ) : (
                <>
                  <div className={`flex flex-col gap-perto ${entrada("")}`}>
                    <h1 className="text-hero font-bold tracking-tight lg:text-hero-lg">
                      Antes de pagar ou responder, confira a mensagem.
                    </h1>
                    <p className="text-destaque">
                      Cole o texto aqui. Você vê na hora se ele tem sinais de golpe e o que
                      fazer agora. Não precisa criar conta.
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
                      onChange={(evento) => setTexto(evento.target.value)}
                      readOnly={estado.situacao === "analisando"}
                      rows={6}
                      placeholder="Por exemplo: “Sua conta será bloqueada hoje. Faça um PIX para regularizar.”"
                      className="campo-mensagem min-h-[11rem] w-full p-5 text-destaque"
                    />
                    <div className="flex flex-wrap items-center gap-x-perto gap-y-junto">
                      <button
                        type="submit"
                        disabled={vazio || estado.situacao === "analisando"}
                        aria-describedby={vazio ? "dica-botao" : undefined}
                        className="botao-principal alvo-de-toque w-full rounded-full px-8 py-3
                          text-destaque font-bold sm:w-auto"
                      >
                        {estado.situacao === "analisando" ? "Analisando…" : "Analisar mensagem"}
                      </button>
                      {/* Diz por que o botão está esperando — sem isto, botão desabilitado
                          parece botão quebrado. */}
                      {vazio && (
                        <p id="dica-botao">Cole uma mensagem para poder analisar.</p>
                      )}
                    </div>
                  </form>
                </>
              )}

              {/* `aria-live` faz o leitor de tela anunciar o resultado sem que a pessoa
                  precise procurá-lo. `polite` para não interromper o que estiver sendo lido. */}
              <section aria-live="polite" className="flex flex-col gap-6">
                {estado.situacao === "analisando" && (
                  <p className="text-destaque">Analisando sua mensagem…</p>
                )}

                {estado.situacao === "falhou" && (
                  <div role="alert" className="cartao border-l-[10px] border-[var(--erro)] p-5">
                    <p className="text-destaque font-bold">Não deu para analisar</p>
                    <p className="mt-1">{estado.mensagem}</p>
                  </div>
                )}

                {estado.situacao === "concluida" && (
                  <Resultado resultado={estado.resultado} tituloRef={tituloDoResultado} />
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
// Espelho de `backend/app/scoring/regras.yaml` (versao: 1), na mesma ordem. `significado` é a
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
  | "dados_pessoais";

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
                  {APRESENTACAO.ALTO.palavra}
                </p>
              </div>
              <div className="flex flex-col gap-perto px-4 py-5">
                <p className="font-bold">{APRESENTACAO.ALTO.resumo}</p>
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
              quais sinais elas procuram.
            </p>
          </div>
          <div className="cartao flex flex-col gap-junto p-bloco">
            <h3 className="text-secao font-bold sm:text-secao-lg">
              Sua mensagem não fica guardada
            </h3>
            <p className="text-destaque">
              Lemos o texto, analisamos e descartamos. Nenhuma cópia fica com a gente.
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
    // Condicional de propósito: nesta fase o texto do resultado é fixo no frontend e a IA
    // ainda não é usada (Fase 7). A frase é verdadeira antes e depois.
    "Quem decide o risco são as regras, não a inteligência artificial. Quando ela é usada, " +
      "só ajuda a escrever o resultado de um jeito fácil — e nunca recebe a mensagem que " +
      "você colou.",
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

/** As seis categorias do motor, em grade de cartões, cada uma com o seu ícone. */
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
            São seis tipos de sinal. Uma mensagem pode ter vários, e cada tipo conta uma vez,
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
          Os links da mensagem ainda não são conferidos. Essa parte está sendo construída.
        </p>
      </div>
    </section>
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
  const urls = resultado.urls_analisadas;

  return (
    <div className="cartao placa-risco entrada-resultado" data-nivel={resultado.nivel_risco}>
      <div className="faixa-risco flex items-center gap-4 px-5 py-5 sm:px-bloco">
        {/* O ícone é decorativo para o leitor de tela: a palavra ao lado já diz tudo, e
            anunciar os dois seria repetição. */}
        <span aria-hidden="true" className="shrink-0">
          <IconeDeRisco nivel={resultado.nivel_risco} />
        </span>
        <h2
          ref={tituloRef}
          tabIndex={-1}
          className="text-veredito font-extrabold sm:text-veredito-lg"
        >
          {palavra}
        </h2>
      </div>

      <div className="flex flex-col gap-bloco px-5 py-6 sm:p-bloco">
        <p className="text-destaque font-semibold">{resumo}</p>

        {/* "O que fazer" vem antes de "Fatores identificados" — o inverso da versão
            anterior — de propósito: quem chega aqui está assustado e precisa primeiro saber
            como se proteger; o porquê (os fatores) vem depois, para quem quiser entender. */}
        <div className="flex flex-col gap-2 rounded-2xl border-2 border-[var(--risco-forte)]
          bg-[var(--risco-fundo)] p-5">
          <h3 className="text-secao font-bold sm:text-secao-lg">O que fazer</h3>
          <p className="text-destaque">{recomendacao}</p>
        </div>

        {resultado.fatores.length > 0 && (
          <div className="flex flex-col gap-3">
            <h3 className="text-secao font-bold sm:text-secao-lg">Fatores identificados</h3>
            {/* Marcador simples, não numeração: os fatores são um conjunto, e números
                sugeririam uma ordem de importância que não existe. */}
            <ul className="flex list-disc flex-col gap-2 pl-6 text-destaque
              marker:text-[var(--risco-forte)]">
              {resultado.fatores.map((fator) => (
                <li key={fator.categoria}>{fator.descricao}</li>
              ))}
            </ul>
          </div>
        )}

        {urls.length > 0 && (
          <div className="flex flex-col gap-3">
            <h3 className="text-secao font-bold sm:text-secao-lg">
              Links que aparecem na mensagem
            </h3>
            {/* Texto, nunca <a>: um link clicável aqui seria um atalho para o próprio golpe.
                A grafia é a forma canônica da API (ADR-0009), que pode diferir da colada. */}
            <ul className="flex flex-col gap-2">
              {urls.map((url) => (
                <li
                  key={url}
                  className="break-all rounded-xl border-2 border-tinta/40 bg-fundo px-4 py-2
                    font-mono"
                >
                  {url}
                </li>
              ))}
            </ul>
            <p>
              {urls.length === 1
                ? "Ainda não conferimos se este site é verdadeiro. "
                : "Ainda não conferimos se estes sites são verdadeiros. "}
              Não abra antes de confirmar com a empresa pelo telefone ou aplicativo oficial.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function IconeDeRisco({ nivel }: { nivel: NivelRisco }) {
  const comum = {
    width: 44,
    height: 44,
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
        <circle cx="12" cy="12" r="9.5" />
        <path d="m7.5 12 3 3 6-6" />
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
      <circle cx="12" cy="12" r="9.5" />
      <path d="m15 9-6 6" />
      <path d="m9 9 6 6" />
    </svg>
  );
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
