// O resultado de uma análise, compartilhado pela home e pelo histórico (ADR-0018): a pessoa vê a
// mesma placa, as mesmas frases e os mesmos fatores hoje e quando voltar à análise depois.

import type { RefObject } from "react";

import { IconeDeRisco, PALAVRA_DO_NIVEL, type NivelRisco } from "./nivel-risco";

/** A resposta fixa do nível, do `respostas.yaml` do backend (ADR-0020): o plano B inteiro quando
 *  a IA não entrou, e o título (e o texto do BAIXO) quando ela entrou. */
export type Orientacao = { titulo: string; texto: string | null; passos: string[] };

/** O que a IA escreveu para esta mensagem, já limpo pelo backend: sem link, e-mail, telefone nem
 *  HTML. Mesmo assim, é texto: o React escapa, e nada aqui vira link nem HTML. */
export type ExplicacaoIA = { tipo: string; sinais: string[]; o_que_fazer: string[] };

/** O que a placa precisa. As URLs só existem na resposta da análise: o banco não as guarda
 *  (ADR-0009), e no histórico elas aparecem dentro da própria mensagem.
 *
 *  `orientacao` e `explicacao_ia` são opcionais só para um backend anterior à fatia 6 (no deploy,
 *  o frontend pode subir antes): sem eles, a placa mostra o nível e os fatores. */
export type DadosDoResultado = {
  nivel_risco: NivelRisco;
  fatores: { categoria: string; descricao: string }[];
  urls_analisadas?: string[];
  orientacao?: Orientacao;
  explicacao_ia?: ExplicacaoIA | null;
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
  const urls = resultado.urls_analisadas ?? [];
  const orientacao = resultado.orientacao;
  const ia = resultado.explicacao_ia ?? null;
  // Com a IA, os passos são os dela, para esta mensagem; sem ela, os fixos do nível. O BAIXO do
  // plano B não tem passos: o texto dele é a recomendação e vai para o quadro "O que fazer".
  const passos = ia ? ia.o_que_fazer : (orientacao?.passos ?? []);
  const textoNoQuadro = passos.length === 0 ? (orientacao?.texto ?? null) : null;
  const textoForaDoQuadro = passos.length > 0 ? (orientacao?.texto ?? null) : null;

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
        {orientacao && (
          <div className="flex flex-col gap-junto">
            <p className="text-destaque font-semibold">{orientacao.titulo}</p>
            {ia && (
              <p className="text-destaque">
                Parece ser: <strong>{ia.tipo}</strong>.
              </p>
            )}
            {/* O aviso do BAIXO ("isso não garante…") fica visível também com a IA: o sistema
                nunca diz que a mensagem é segura. */}
            {textoForaDoQuadro && <p className="text-destaque">{textoForaDoQuadro}</p>}
          </div>
        )}

        {/* "O que fazer" vem antes dos sinais e dos fatores de propósito: quem chega aqui está
            assustado e precisa primeiro saber como se proteger; o porquê vem depois. */}
        {(passos.length > 0 || textoNoQuadro) && (
          <div className="flex flex-col gap-2 rounded-2xl border-2 border-[var(--risco-forte)]
            bg-[var(--risco-fundo)] p-5">
            <Subtitulo className="text-secao font-bold sm:text-secao-lg">O que fazer</Subtitulo>
            {passos.length > 0 ? (
              <ul className="flex list-disc flex-col gap-2 pl-6 text-destaque
                marker:text-[var(--risco-forte)]">
                {passos.map((passo) => (
                  <li key={passo}>{passo}</li>
                ))}
              </ul>
            ) : (
              <p className="text-destaque">{textoNoQuadro}</p>
            )}
          </div>
        )}

        {ia && ia.sinais.length > 0 && (
          <div className="flex flex-col gap-3">
            <Subtitulo className="text-secao font-bold sm:text-secao-lg">
              O que chamou a atenção
            </Subtitulo>
            <ul className="flex list-disc flex-col gap-2 pl-6 text-destaque
              marker:text-[var(--risco-forte)]">
              {ia.sinais.map((sinal) => (
                <li key={sinal}>{sinal}</li>
              ))}
            </ul>
          </div>
        )}

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

        {/* Discreta e honesta: diz que a IA ajudou, sem selo nem destaque. Na cor do texto, como
            todo o resto (nada de cinza, globals.css). */}
        {ia && <p>Análise com apoio de IA.</p>}
      </div>
    </div>
  );
}
