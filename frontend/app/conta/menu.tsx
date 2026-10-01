"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const SECOES = [
  { href: "/conta/historico", rotulo: "Histórico" },
  { href: "/conta/dados", rotulo: "Meus dados" },
  { href: "/conta/privacidade", rotulo: "Privacidade" },
] as const;

const PILULA =
  "alvo-de-toque inline-flex items-center justify-center rounded-full px-3 text-center " +
  "font-bold md:justify-start md:px-5";

/** Menu da área da conta: links de verdade, cada seção com URL própria (ADR-0016).
 *
 *  Não é o padrão ARIA de abas: abas trocam painel sem trocar de página, e aqui cada item é uma
 *  página — o voltar do navegador funciona e o leitor de tela anuncia "link, página atual". */
export function MenuConta() {
  const caminho = usePathname();

  return (
    // Abaixo de 768 px, grade de 2 colunas acima do painel; a partir daí, coluna à esquerda.
    <nav aria-label="Minha conta" className="grid grid-cols-2 gap-junto md:flex md:flex-col">
      {SECOES.map((secao) => {
        const atual = caminho === secao.href;
        return (
          <Link
            key={secao.href}
            href={secao.href}
            aria-current={atual ? "page" : undefined}
            className={`${PILULA} ${atual ? "botao-principal" : "botao-secundario"}`}
          >
            {secao.rotulo}
          </Link>
        );
      })}
    </nav>
  );
}
