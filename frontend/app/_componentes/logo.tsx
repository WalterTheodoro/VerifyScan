import { Sora } from "next/font/google";

// Logo do VerifyScan: o símbolo (os quatro cantos de um visor de scanner, com um check no meio)
// e o nome escrito. A Sora é carregada só aqui — a fonte do resto da página continua a
// Atkinson Hyperlegible, escolhida para o público.
const sora = Sora({ subsets: ["latin", "latin-ext"], weight: ["400", "700"] });

type Variante = "light" | "dark";

/** Cores por variante. Contraste do nome, conferido por script:
 *    light  Verify #0E1A3A/branco 17,1 · Scan #2E55F5/branco 5,6
 *           (sobre o cabeçalho desfocado, no pior caso: 12,7 · 4,2)
 *    dark   Verify branco/anil-profundo 14,3 · Scan #7D98FF/anil-profundo 5,3
 *  No tamanho do cabeçalho o nome tem 24px — texto grande, piso AA de 3:1. */
const CORES: Record<Variante, { moldura: string; check: string; verify: string; scan: string }> =
  {
    light: { moldura: "#0E1A3A", check: "#2E55F5", verify: "#0E1A3A", scan: "#2E55F5" },
    dark: { moldura: "#FFFFFF", check: "#7D98FF", verify: "#FFFFFF", scan: "#7D98FF" },
  };

export function Logo({
  variant = "light",
  size = 32,
  markOnly = false,
  className = "",
}: {
  variant?: Variante;
  /** Altura do símbolo, em px. O nome acompanha: 75% dela. */
  size?: number;
  markOnly?: boolean;
  className?: string;
}) {
  const cores = CORES[variant];
  // Em tamanho pequeno o traço engrossa, para o símbolo não sumir.
  const pequeno = size <= 40;

  return (
    <span
      className={`inline-flex items-center ${className}`}
      style={{ gap: size * 0.31 }}
      // Só o símbolo não tem texto; aí o nome vem do rótulo. `role="img"` é o que faz o
      // `aria-label` de um <span> ser lido.
      {...(markOnly ? { role: "img", "aria-label": "VerifyScan" } : {})}
    >
      <svg
        width={size}
        height={size}
        viewBox="0 0 64 64"
        fill="none"
        aria-hidden="true"
        focusable="false"
        className="shrink-0"
      >
        <path
          d="M6 20V10a4 4 0 0 1 4-4h10M44 6h10a4 4 0 0 1 4 4v10M58 44v10a4 4 0 0 1-4 4H44M20 58H10a4 4 0 0 1-4-4V44"
          stroke={cores.moldura}
          strokeWidth={pequeno ? 6 : 5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M19.5 33l8.5 8.5L45 24.5"
          stroke={cores.check}
          strokeWidth={pequeno ? 7.5 : 6.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {!markOnly && (
        // Texto de verdade, não desenho: o leitor de tela lê o nome direto daqui.
        <span
          className={sora.className}
          style={{ fontSize: size * 0.75, letterSpacing: "-0.03em", lineHeight: 1 }}
        >
          <span style={{ fontWeight: 700, color: cores.verify }}>Verify</span>
          <span style={{ fontWeight: 400, color: cores.scan }}>Scan</span>
        </span>
      )}
    </span>
  );
}
