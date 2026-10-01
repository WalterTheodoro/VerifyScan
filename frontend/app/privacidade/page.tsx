import type { Metadata } from "next";

import { Cabecalho } from "../_componentes/cabecalho";
import { Rodape } from "../_componentes/rodape";
import { RaizDaPagina } from "../_componentes/raiz-da-pagina";

export const metadata: Metadata = { title: "Aviso de privacidade — VerifyScan" };

// NEXT_PUBLIC_ porque a página é gerada no build e o valor entra no HTML. Sem a variável, a
// página continua de pé e diz que o contato está em configuração.
const CONTATO = process.env.NEXT_PUBLIC_CONTATO_PRIVACIDADE?.trim() ?? "";

const LINK = "font-bold text-anil underline underline-offset-4 break-all";

/** Aviso curto, em pt-BR simples. O que está aqui precisa bater com o banco: models/ e
 *  ADR-0006 (análise sem texto), ADR-0013 (conta e sessão), ADR-0011 (Neon). */
export default function PaginaPrivacidade() {
  return (
    <RaizDaPagina>
      <Cabecalho />
      <main className="fundo-hero flex-1">
        <div className="mx-auto flex w-full max-w-[44rem] flex-col gap-bloco px-5 pb-secao
          pt-bloco">
          <h1 className="text-titulo font-bold sm:text-titulo-lg">Aviso de privacidade</h1>

          <div className="cartao flex flex-col gap-bloco p-5 text-destaque sm:p-bloco">
            <section aria-labelledby="com-conta" className="flex flex-col gap-junto">
              <h2 id="com-conta" className="text-secao font-bold sm:text-secao-lg">
                Se você criar uma conta, guardamos
              </h2>
              <ul className="flex list-disc flex-col gap-junto pl-6">
                <li>o nome que você escolheu para ser chamado;</li>
                <li>o seu e-mail;</li>
                <li>
                  a sua senha, mas só embaralhada de um jeito que não dá para desfazer (uma
                  técnica chamada Argon2id). Nem nós conseguimos ver a sua senha;
                </li>
                <li>
                  uma sessão que mantém você conectado neste navegador por até 7 dias. Ao
                  tocar em &ldquo;Sair&rdquo;, ela é apagada.
                </li>
              </ul>
            </section>

            <section aria-labelledby="analises" className="flex flex-col gap-junto">
              <h2 id="analises" className="text-secao font-bold sm:text-secao-lg">
                Das análises, guardamos
              </h2>
              <p>
                Só o nível de risco, a pontuação, os sinais encontrados e a data.{" "}
                <strong>Nunca o texto da mensagem que você colou.</strong>
              </p>
            </section>

            <section aria-labelledby="onde" className="flex flex-col gap-junto">
              <h2 id="onde" className="text-secao font-bold sm:text-secao-lg">
                Onde ficam
              </h2>
              <p>
                Em servidores nos Estados Unidos, de duas empresas: Render, onde o site roda, e
                Neon, onde fica o banco de dados.
              </p>
            </section>

            <section aria-labelledby="compartilhar" className="flex flex-col gap-junto">
              <h2 id="compartilhar" className="text-secao font-bold sm:text-secao-lg">
                Com quem
              </h2>
              <p>Com ninguém. Não vendemos nem compartilhamos os seus dados.</p>
            </section>

            <section aria-labelledby="apagar" className="flex flex-col gap-junto">
              <h2 id="apagar" className="text-secao font-bold sm:text-secao-lg">
                Para apagar a sua conta e os seus dados
              </h2>
              {CONTATO ? (
                <p>
                  Escreva para{" "}
                  <a href={`mailto:${CONTATO}`} className={LINK}>
                    {CONTATO}
                  </a>
                  .
                </p>
              ) : (
                <p>Escreva para o nosso contato, que está em configuração.</p>
              )}
            </section>
          </div>
        </div>
      </main>
      <Rodape />
    </RaizDaPagina>
  );
}
