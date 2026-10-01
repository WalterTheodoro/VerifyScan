"use client";

import Link from "next/link";
import { useRef } from "react";

import { AvisosDoEnvio } from "../../_componentes/avisos-do-envio";
import { buscarConta, formatarData, HISTORICO_DIAS } from "../../_lib/historico";
import { useCarga } from "../../_lib/use-carga";
import { AvisoEntrar } from "../aviso-entrar";

/** Seção Meus dados: só leitura. Editar nome ou e-mail está fora desta fatia.
 *
 *  Sem texto cinza (regra do globals.css): rótulo e valor se distinguem por tamanho e peso. */
export function DadosDaConta() {
  const { carga, demorando } = useCarga(buscarConta);
  const avisoDeErro = useRef<HTMLDivElement>(null);

  if (carga.situacao === "deslogado") {
    return <AvisoEntrar />;
  }

  return (
    <section aria-labelledby="titulo-dados" className="flex flex-col gap-bloco">
      {/* Os avisos ficam no grupo do título: vazios, também contariam no espaçamento. */}
      <div className="flex flex-col gap-junto">
        <h2 id="titulo-dados" className="text-secao font-bold sm:text-secao-lg">
          Meus dados
        </h2>
        <AvisosDoEnvio
          demorando={demorando}
          erro={carga.situacao === "erro" ? carga.mensagem : null}
          avisoDeErro={avisoDeErro}
        />
      </div>

      {carga.situacao === "carregando" && !demorando && <p>Carregando os seus dados…</p>}

      {carga.situacao === "ok" && (
        <>
          {/* Identificação. `min-w-0` deixa o texto encolher e truncar em vez de empurrar o
              cartão: o nome tem até 60 caracteres e o e-mail até 254. */}
          <div className="flex min-w-0 items-center gap-perto">
            {/* Decorativa: o nome já está escrito ao lado. */}
            <span aria-hidden="true"
              className="flex h-[56px] w-[56px] shrink-0 items-center justify-center rounded-full
                bg-lavanda-clara text-secao font-bold text-anil">
              {inicial(carga.dados.nome)}
            </span>
            <div className="flex min-w-0 flex-col">
              <p className="truncate text-secao font-bold">{carga.dados.nome}</p>
              <p className="truncate">{carga.dados.email}</p>
            </div>
          </div>

          {/* Linhas separadas por um fio. Abaixo de 640 px, rótulo em cima do valor. */}
          <dl className="border-t border-lavanda">
            <Linha rotulo="Nome de exibição" valor={carga.dados.nome} />
            <Linha rotulo="E-mail" valor={carga.dados.email} />
            <Linha rotulo="Conta criada em" valor={formatarData(carga.dados.criado_em)} />
            <Linha rotulo="Histórico guardado por" valor={`${HISTORICO_DIAS} dias`} />
          </dl>

          {/* Quadro à parte: não é um dado da conta. Na fatia 5, os botões de excluir a conta
              entram aqui, e esta frase sai. */}
          <div className="rounded-2xl bg-lavanda-clara p-5">
            <p>
              Para apagar a sua conta, veja a seção{" "}
              <Link href="/conta/privacidade"
                className="font-bold text-anil underline underline-offset-4">
                Privacidade
              </Link>
              .
            </p>
          </div>
        </>
      )}
    </section>
  );
}

function Linha({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div className="flex flex-col gap-1 border-b border-lavanda py-perto sm:flex-row
      sm:items-baseline sm:justify-between sm:gap-bloco">
      <dt className="shrink-0">{rotulo}</dt>
      {/* `overflow-wrap: anywhere`: um e-mail sem espaço quebra dentro do cartão. */}
      <dd className="min-w-0 text-destaque font-semibold [overflow-wrap:anywhere] sm:text-right">
        {valor}
      </dd>
    </div>
  );
}

/** A primeira letra, inteira mesmo fora do plano básico do Unicode (Array.from, não [0]). */
function inicial(nome: string): string {
  return (Array.from(nome.trim())[0] ?? "").toLocaleUpperCase("pt-BR");
}
