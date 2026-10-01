"use client";

import Link from "next/link";

import { AreaSessao } from "./area-sessao";
import { Logo } from "./logo";

// Sem `inline-flex` aqui: ele vem depois de `hidden` no CSS gerado e venceria, deixando as âncoras
// sempre visíveis. O `display` das âncoras fica só no `hidden xl:inline-flex` do uso.
const ANCORA =
  "alvo-de-toque items-center rounded-full px-4 font-semibold " +
  "transition-colors duration-150 hover:bg-lavanda-clara";

const BOTAO_ANALISAR = "botao-principal alvo-de-toque ml-2 rounded-full px-5 font-bold";

/** Na home, o logo rola até o topo em vez de navegar para a mesma página. Suave só para quem
 *  não pediu menos movimento (ADR-0010). */
function aoClicarLogoNaHome(evento: React.MouseEvent<HTMLAnchorElement>) {
  evento.preventDefault();
  const semMovimento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  window.scrollTo({ top: 0, behavior: semMovimento ? "auto" : "smooth" });
}

/** Fixo no topo. Só o que existe: o nome, duas âncoras para seções da home, o atalho para o
 *  campo e a área de sessão.
 *
 *  Na home, `aoIrParaAnalise` rola até o campo sem sair da página. Nas outras páginas ele não
 *  vem, e os mesmos itens viram links para a home — mesmo visual, outro destino. */
export function Cabecalho({ aoIrParaAnalise }: { aoIrParaAnalise?: () => void }) {
  const naHome = aoIrParaAnalise !== undefined;
  // Abaixo de 640 px o rótulo visível é só "Analisar"; o nome acessível continua inteiro, pelo
  // `aria-label`. O <span> de fora é necessário: no link (inline-flex), "Analisar" e o span
  // interno virariam itens flex separados, e o espaço antes de "mensagem" seria descartado.
  const rotuloAnalisar = (
    <span>
      Analisar<span className="hidden sm:inline"> mensagem</span>
    </span>
  );

  return (
    // Fixo só a partir de 640 px. No celular estreito ele chega a 165 px (logado, em 320 px):
    // fixo, cobriria o destino das âncoras e o foco (WCAG 2.4.11) e tiraria quase um terço da
    // tela de quem lê o resultado. O `scroll-padding-top` do globals.css acompanha esta regra.
    <header className="cabecalho top-0 z-50 sm:sticky">
      {/* Uma linha que quebra quando não cabe: o logo empurra o resto para a direita
          (`mr-auto`), e a área de sessão, quando desce, fica alinhada à direita. */}
      <div className="mx-auto flex w-full max-w-[72rem] flex-wrap items-center justify-end
        gap-x-1 gap-y-1 px-5 py-2.5 lg:px-8">
        <Link
          href="/"
          onClick={naHome ? aoClicarLogoNaHome : undefined}
          className="alvo-de-toque mr-auto inline-flex shrink-0 items-center"
          aria-label="VerifyScan, página inicial"
        >
          <Logo />
        </Link>
        {/* As âncoras só a partir de 1280 px (xl). Medido no navegador: a linha inteira — logo,
            as duas âncoras, "Analisar mensagem" e a sessão com nome longo — ocupa ~1.195 px e só
            cabe nos 1.208 px de conteúdo do xl; em 1024 px sobram 952. Abaixo disso as duas
            seções seguem a uma rolagem da home; menu hambúrguer ficou fora desta correção. */}
        <nav aria-label={naHome ? "Nesta página" : "Página inicial"}
          className="flex items-center gap-1">
          <a href={naHome ? "#como-funciona" : "/#como-funciona"}
            className={`${ANCORA} hidden xl:inline-flex`}>
            Como funciona
          </a>
          <a href={naHome ? "#o-que-procura" : "/#o-que-procura"}
            className={`${ANCORA} hidden xl:inline-flex`}>
            O que ele procura
          </a>
          {naHome ? (
            <button type="button" onClick={aoIrParaAnalise} aria-label="Analisar mensagem"
              className={BOTAO_ANALISAR}>
              {rotuloAnalisar}
            </button>
          ) : (
            // O Next rola até a âncora ao chegar, sem dar foco ao campo: no celular, foco
            // no campo abriria o teclado sem a pessoa pedir.
            <Link href="/#analisar" aria-label="Analisar mensagem"
              className={`${BOTAO_ANALISAR} inline-flex items-center`}>
              {rotuloAnalisar}
            </Link>
          )}
        </nav>
        {/* Abaixo de 768 px a sessão fica SEMPRE na própria linha (`basis-full`), carregando,
            deslogada ou logada: a altura do cabeçalho não depende da resposta de /api/auth/eu,
            e a página não salta quando ela chega. A partir de 768 px os três estados cabem na
            primeira linha. */}
        <div className="min-w-0 basis-full md:ml-2 md:basis-auto">
          <AreaSessao />
        </div>
      </div>
    </header>
  );
}
