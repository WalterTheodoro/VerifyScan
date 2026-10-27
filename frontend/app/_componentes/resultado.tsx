// O resultado de uma análise, compartilhado pela home e pelo histórico (ADR-0018): a pessoa vê a
// mesma placa, as mesmas frases e os mesmos fatores hoje e quando voltar à análise depois.

import type { RefObject } from "react";

import { IconeDeRisco, PALAVRA_DO_NIVEL, type NivelRisco } from "./nivel-risco";

/** O que a placa precisa. As URLs só existem na resposta da análise: o banco não as guarda
 *  (ADR-0009), e no histórico elas aparecem dentro da própria mensagem. */
export type DadosDoResultado = {
  nivel_risco: NivelRisco;
  fatores: { categoria: string; descricao: string }[];
  urls_analisadas?: string[];
};

/** Texto exibido para cada nível; a palavra e o ícone vêm de `nivel-risco`.
 *  O tom acalma sem minimizar: quem lê isto pode estar com medo de já ter perdido dinheiro. */
export const APRESENTACAO: Record<NivelRisco, { resumo: string; recomendacao: string }> = {
  BAIXO: {
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
    resumo: "Esta mensagem tem sinais que pedem cuidado.",
    recomendacao:
      "Por enquanto, não clique em links e não passe seus dados. Confirme com a empresa, " +
      "pelo telefone ou aplicativo oficial, se a mensagem é verdadeira.",
  },
  ALTO: {
    resumo: "Esta mensagem tem sinais fortes de golpe. Você fez bem em conferir antes.",
    recomendacao:
      "Não clique no link, não pague nada e não passe seus dados. Apague a mensagem e " +
      "bloqueie quem enviou. Se já pagou ou passou algum dado, ligue para o seu banco pelo " +
      "número que está no verso do cartão.",
  },
};

/** "Você colou:" e a mensagem, como texto: um link dentro dela nunca vira <a>. Quem chama decide
 *  a moldura. */
export function MensagemColada({ texto }: { texto: string }) {
  return (
    <>
      <p className="font-bold">Você colou:</p>
      <blockquote
        // `anywhere`, e não `break-word`: um link longo sem espaço quebra também dentro de flex.
        className="whitespace-pre-wrap border-l-4 border-anil py-1 pl-5 text-destaque
          [overflow-wrap:anywhere]"
      >
        {texto}
      </blockquote>
    </>
  );
}

/** A placa do resultado. `nivel` é o do título do veredito: 2 na home (abaixo do h1), 3 no
 *  histórico (abaixo do h2 "Histórico"); os subtítulos descem um nível junto. */
export function Resultado({
  resultado,
  nivel = 2,
  tituloRef,
  animar = false,
}: {
  resultado: DadosDoResultado;
  nivel?: 2 | 3;
  tituloRef?: RefObject<HTMLHeadingElement | null>;
  animar?: boolean;
}) {
  const Titulo = nivel === 2 ? "h2" : "h3";
  const Subtitulo = nivel === 2 ? "h3" : "h4";
  const { resumo, recomendacao } = APRESENTACAO[resultado.nivel_risco];
  const urls = resultado.urls_analisadas ?? [];

  return (
    <div
      className={`cartao placa-risco ${animar ? "entrada-resultado" : ""}`}
      data-nivel={resultado.nivel_risco}
    >
      <div className="faixa-risco flex items-center gap-4 px-5 py-5 sm:px-bloco">
        {/* O ícone é decorativo para o leitor de tela: a palavra ao lado já diz tudo, e
            anunciar os dois seria repetição. */}
        <span aria-hidden="true" className="shrink-0">
          <IconeDeRisco nivel={resultado.nivel_risco} />
        </span>
        <Titulo
          ref={tituloRef}
          tabIndex={tituloRef ? -1 : undefined}
          className="text-veredito font-extrabold sm:text-veredito-lg"
        >
          {PALAVRA_DO_NIVEL[resultado.nivel_risco]}
        </Titulo>
      </div>

      <div className="flex flex-col gap-bloco px-5 py-6 sm:p-bloco">
        <p className="text-destaque font-semibold">{resumo}</p>

        {/* "O que fazer" vem antes de "Fatores identificados" de propósito: quem chega aqui está
            assustado e precisa primeiro saber como se proteger; o porquê vem depois. */}
        <div className="flex flex-col gap-2 rounded-2xl border-2 border-[var(--risco-forte)]
          bg-[var(--risco-fundo)] p-5">
          <Subtitulo className="text-secao font-bold sm:text-secao-lg">O que fazer</Subtitulo>
          <p className="text-destaque">{recomendacao}</p>
        </div>

        {resultado.fatores.length > 0 && (
          <div className="flex flex-col gap-3">
            <Subtitulo className="text-secao font-bold sm:text-secao-lg">
              Fatores identificados
            </Subtitulo>
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
            <Subtitulo className="text-secao font-bold sm:text-secao-lg">
              Links que aparecem na mensagem
            </Subtitulo>
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
