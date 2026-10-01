import Link from "next/link";

/** Rodapé de todas as páginas, com o link para o aviso de privacidade. */
export function Rodape() {
  return (
    <footer className="faixa-escura flex flex-col items-center gap-junto px-5 py-bloco
      text-center">
      <p>Trabalho de conclusão de curso de Engenharia de Software, Católica SC.</p>
      {/* Branco sobre anil-profundo: 14,3:1. Sublinhado para ser link sem depender de cor. */}
      <Link href="/privacidade"
        className="alvo-de-toque inline-flex items-center font-semibold underline
          underline-offset-4">
        Aviso de privacidade
      </Link>
    </footer>
  );
}
