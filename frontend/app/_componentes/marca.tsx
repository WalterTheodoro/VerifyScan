// Marca tipográfica do VerifyScan: o nome escrito, com "Scan" passado a marca-texto — o mesmo
// traço que a página usa para marcar um sinal suspeito. A marca faz, no próprio nome, o que o
// produto faz na mensagem da pessoa. Não há símbolo à parte.
//
// A pasta `_componentes` começa com "_" para o App Router não tratá-la como rota.

// ── O traço de marca-texto ──────────────────────────────────────────────────────────────────
// Três peças, todas com 24 de altura: uma ponta esquerda e uma direita, irregulares e de
// largura fixa, e um miolo repetível. As bordas do miolo em x=0 e x=60 são idênticas às das
// pontas, então as peças se encaixam em qualquer quantidade.
//
// Por que em peças, e não um desenho só esticado: no texto corrido o traço é fundo de CSS, um
// por fragmento de linha, e um trecho de três letras receberia o mesmo desenho comprimido que
// um de trinta — a irregularidade viraria borrão. Com pontas fixas e miolo repetido, trecho
// curto e trecho longo têm as mesmas pontas; só muda quantas vezes o miolo se repete.
//
// ESTES PATHS ESTÃO DUPLICADOS em dois lugares, que citam as constantes pelo nome:
//   • `app/globals.css`, regra `.trecho-marcado`, como SVG embutido em `url(data:…)` — lá o
//     traço precisa ser fundo, porque um trecho marcado pode quebrar linha;
//   • `app/icon.svg`, o favicon vetorial, que não pode importar TypeScript.
// Ao mudar um path aqui, mude o de mesmo nome nos dois. O `favicon.ico` é bitmap desenhado
// à parte (16px pixel a pixel) e não segue o path automaticamente — refaça-o à mão.

/** Ponta esquerda. viewBox 0 0 6 24. */
export const GRIFO_PONTA_ESQUERDA =
  "M6 2.6V21.8C4.6 21.9 3.2 22.3 1.9 21.4C0.9 19.6 1.4 17.2 0.7 15C0.3 12.4 1.2 9.8 0.8 " +
  "7.4C0.6 5.4 1.3 3.6 2.6 2.9C3.7 2.5 4.9 2.6 6 2.6Z";

/** Miolo repetível. viewBox 0 0 60 24. Ondulação sutil de propósito: é ela que se repete. */
export const GRIFO_MIOLO =
  "M0 2.6C10 2.3 20 2.2 30 2.6S50 3 60 2.6V21.8C50 22.1 40 22.2 30 21.8S10 21.5 0 21.8Z";

/** Ponta direita. viewBox 0 0 6 24. */
export const GRIFO_PONTA_DIREITA =
  "M0 2.6C1.4 2.5 2.8 2.2 3.9 3.1C5.2 4.6 4.8 7.1 5.3 9.4C5.7 12 4.9 14.6 5.4 17C5.6 19.3 " +
  "4.9 21 3.6 21.6C2.4 22.1 1.2 21.9 0 21.8Z";

/** O traço inteiro para uma palavra: ponta + um miolo + ponta (viewBox 0 0 72 24). Esticar
 *  aqui é seguro — a palavra é fixa e a proporção fica perto da de um miolo só. */
export function Grifo({ cor, className }: { cor: string; className?: string }) {
  return (
    <svg
      viewBox="0 0 72 24"
      preserveAspectRatio="none"
      aria-hidden="true"
      focusable="false"
      className={className}
    >
      <g fill={cor}>
        <path d={GRIFO_PONTA_ESQUERDA} />
        <path d={GRIFO_MIOLO} transform="translate(6 0)" />
        <path d={GRIFO_PONTA_DIREITA} transform="translate(66 0)" />
      </g>
    </svg>
  );
}

// ── A marca ─────────────────────────────────────────────────────────────────────────────────

export type VarianteMarca = "cor" | "mono" | "sobre-escuro";

/** Cores por variante. O traço cobre a palavra "Scan" inteira, de cima a baixo — como nos
 *  trechos marcados da página —, então "Scan" é sempre lido sobre o traço, nunca sobre o fundo.
 *  É isso que salva a variante escura: branco sobre o rosa daria 1,5:1.
 *
 *    cor           Verify tinta/branco 15,7 · Scan anil/rosa 5,4
 *    mono          Verify tinta/branco 15,7 · Scan tinta/cinza 10,8   (impressão, monografia)
 *    sobre-escuro  Verify branco/anil-profundo 14,3 · Scan anil-profundo/rosa 9,5
 *
 *  A marca é texto grande (≥ 26px, peso 800): o piso AA para ela é 3:1. Todas passam de 5. */
const CORES: Record<VarianteMarca, { verify: string; scan: string; grifo: string }> = {
  cor: { verify: "var(--tinta)", scan: "var(--anil)", grifo: "var(--rosa-marcador)" },
  mono: { verify: "var(--tinta)", scan: "var(--tinta)", grifo: "#d4d6dc" },
  "sobre-escuro": {
    verify: "#ffffff",
    scan: "var(--anil-profundo)",
    grifo: "var(--rosa-marcador)",
  },
};

/** O nome do produto. O tamanho vem de fora (`className`), a partir do tamanho da fonte.
 *
 *  Para leitor de tela a marca é o nome, não um desenho: o desenho inteiro é `aria-hidden` e o
 *  nome entra como texto em `sr-only`. Sem isso, "Verify" e "Scan" em elementos separados
 *  podem ser lidos como duas palavras.
 *
 *  "S" maiúsculo, de propósito: sem espaço no nome, é a maiúscula que mostra onde "Verify"
 *  termina e "Scan" começa — e o traço começa exatamente ali. */
export function Marca({
  variante = "cor",
  className = "",
}: {
  variante?: VarianteMarca;
  className?: string;
}) {
  const cores = CORES[variante];

  return (
    <span className={`inline-block font-extrabold leading-none tracking-[-0.02em] ${className}`}>
      <span className="sr-only">VerifyScan</span>
      <span aria-hidden="true" className="inline-flex items-baseline">
        <span style={{ color: cores.verify }}>Verify</span>
        {/* `isolate` cria o contexto de empilhamento que deixa o traço (z negativo) atrás das
            letras, mas não atrás do fundo da página. O respiro à esquerda separa o traço do
            "y", que desce abaixo da linha. */}
        <span
          className="relative isolate ml-[0.08em] px-[0.14em]"
          style={{ color: cores.scan }}
        >
          <Grifo
            cor={cores.grifo}
            className="absolute inset-x-0 -top-[0.16em] -z-10 h-[calc(100%+0.3em)] w-full"
          />
          Scan
        </span>
      </span>
    </span>
  );
}
