// Vocabulário visual do nível de risco, compartilhado pelo resultado da home e pelo histórico.
// Nunca só a cor: a palavra e o ícone carregam o sentido (ADR-0010). As cores ficam no CSS, em
// `.placa-risco[data-nivel]`.

export type NivelRisco = "BAIXO" | "MEDIO" | "ALTO";

/** A palavra por extenso. Sem acento no fio ("MEDIO"); a tela é que escreve "médio". */
export const PALAVRA_DO_NIVEL: Record<NivelRisco, string> = {
  BAIXO: "Risco baixo",
  MEDIO: "Risco médio",
  ALTO: "Risco alto",
};

export function IconeDeRisco({ nivel, tamanho = 44 }: { nivel: NivelRisco; tamanho?: number }) {
  const comum = {
    width: tamanho,
    height: tamanho,
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
