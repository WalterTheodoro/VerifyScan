"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { AvisosDoEnvio } from "../../_componentes/avisos-do-envio";
import { CampoSenha } from "../../_componentes/campo-senha";
import { marcarContaExcluida } from "../../_lib/conta-excluida";
import { excluirConta, trocarSenha } from "../../_lib/gestao-conta";
import { buscarConta, formatarData, HISTORICO_DIAS } from "../../_lib/historico";
import { useCarga } from "../../_lib/use-carga";
import { useEnvio } from "../../_lib/use-envio-conta";
import { AvisoEntrar } from "../aviso-entrar";

const BOTAO = "alvo-de-toque inline-flex items-center justify-center rounded-full px-5 font-bold";
const TITULO_DE_SECAO = "text-secao font-bold sm:text-secao-lg";

/** Seção Meus dados: os dados da conta (só leitura), trocar a senha e excluir a conta (ADR-0019).
 *  Editar nome ou e-mail está fora desta fatia.
 *
 *  Sem texto cinza (regra do globals.css): rótulo e valor se distinguem por tamanho e peso. */
export function DadosDaConta() {
  const { carga, definir, demorando } = useCarga(buscarConta);
  const avisoDeErro = useRef<HTMLDivElement>(null);
  // A sessão pode vencer com a página aberta: qualquer 401 de um envio vira "Entre na sua conta".
  const aoDeslogar = () => definir({ situacao: "deslogado" });

  if (carga.situacao === "deslogado") {
    return <AvisoEntrar />;
  }

  return (
    <section aria-labelledby="titulo-dados" className="flex flex-col gap-bloco">
      {/* Os avisos ficam no grupo do título: vazios, também contariam no espaçamento. */}
      <div className="flex flex-col gap-junto">
        <h2 id="titulo-dados" className={TITULO_DE_SECAO}>
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

          <TrocarSenha aoDeslogar={aoDeslogar} />
          <ExcluirConta aoDeslogar={aoDeslogar} />
        </>
      )}
    </section>
  );
}

/** Senha atual e nova senha. Em caso de sucesso, os campos ficam vazios e o anúncio diz que as
 *  outras sessões foram encerradas: é o que quem troca a senha por desconfiança precisa saber. */
function TrocarSenha({ aoDeslogar }: { aoDeslogar: () => void }) {
  const [senhaAtual, setSenhaAtual] = useState("");
  const [novaSenha, setNovaSenha] = useState("");
  const [anuncio, setAnuncio] = useState("");
  const { enviando, demorando, erro, avisoDeErro, enviar, falhar, concluir } = useEnvio();

  function aoEnviar(evento: React.FormEvent) {
    evento.preventDefault();
    setAnuncio("");
    void enviar((opcoes) => trocarSenha(senhaAtual, novaSenha, opcoes)).then((resultado) => {
      if (resultado.situacao === "deslogado") {
        aoDeslogar();
        return;
      }
      if (resultado.situacao === "erro") {
        falhar(resultado.mensagem);
        return;
      }
      concluir();
      setSenhaAtual("");
      setNovaSenha("");
      setAnuncio("Senha trocada. Você saiu das outras sessões abertas.");
    });
  }

  return (
    <section aria-labelledby="titulo-trocar-senha"
      className="flex flex-col gap-perto border-t-2 border-lavanda pt-bloco">
      <h3 id="titulo-trocar-senha" className={TITULO_DE_SECAO}>
        Trocar senha
      </h3>
      {/* `noValidate`: quem valida é o backend, que já responde em pt-BR (ADR-0013). */}
      <form onSubmit={aoEnviar} noValidate className="flex flex-col gap-bloco">
        <CampoSenha
          id="senha-atual"
          nome="senha-atual"
          rotulo="Senha atual"
          autoComplete="current-password"
          valor={senhaAtual}
          aoMudar={setSenhaAtual}
          somenteLeitura={enviando}
        />
        {/* Campo e avisos num grupo só: vazios, os avisos não abrem um buraco no espaçamento. */}
        <div className="flex flex-col gap-perto">
          {/* A regra vem antes de qualquer erro. O número é o mesmo do backend (ADR-0013 §5). */}
          <CampoSenha
            id="nova-senha"
            nome="nova-senha"
            rotulo="Nova senha"
            autoComplete="new-password"
            valor={novaSenha}
            aoMudar={setNovaSenha}
            somenteLeitura={enviando}
            dica="Use pelo menos 8 caracteres."
          />
          {/* Sempre montada: região criada junto com o conteúdo não é anunciada. */}
          <p aria-live="polite" className={anuncio ? "font-semibold" : "sr-only"}>
            {anuncio}
          </p>
          <AvisosDoEnvio demorando={demorando} erro={erro} avisoDeErro={avisoDeErro} />
        </div>

        <button type="submit" disabled={enviando}
          className={`${BOTAO} botao-principal w-full sm:w-auto sm:self-start`}>
          {enviando ? "Trocando…" : "Trocar senha"}
        </button>
      </form>
    </section>
  );
}

/** Excluir a conta, no quadro lavanda. A confirmação abre no próprio quadro, sem janela por
 *  cima (a mesma regra do histórico), e pede a senha: no celular dividido com a família, sessão
 *  aberta sozinha não basta para apagar tudo (ADR-0019). */
function ExcluirConta({ aoDeslogar }: { aoDeslogar: () => void }) {
  const router = useRouter();
  const [confirmando, setConfirmando] = useState(false);
  const [senha, setSenha] = useState("");
  const { enviando, demorando, erro, avisoDeErro, enviar, falhar } = useEnvio();
  const botaoAbrir = useRef<HTMLButtonElement>(null);
  const botaoCancelar = useRef<HTMLButtonElement>(null);

  function abrir() {
    setConfirmando(true);
    // O foco vai para "Cancelar": Enter sem querer não apaga nada.
    requestAnimationFrame(() => botaoCancelar.current?.focus());
  }

  function cancelar() {
    setConfirmando(false);
    setSenha("");
    requestAnimationFrame(() => botaoAbrir.current?.focus());
  }

  function aoConfirmar(evento: React.FormEvent) {
    evento.preventDefault();
    void enviar((opcoes) => excluirConta(senha, opcoes)).then((resultado) => {
      if (resultado.situacao === "deslogado") {
        aoDeslogar();
        return;
      }
      if (resultado.situacao === "erro") {
        falhar(resultado.mensagem);
        return;
      }
      // O botão segue em "Excluindo…" até a home abrir, já deslogada (o 204 limpou o cookie).
      // O aviso vai por sessionStorage, nunca pela URL (ADR-0019).
      marcarContaExcluida();
      router.push("/");
    });
  }

  return (
    <section aria-labelledby="titulo-excluir"
      className="flex flex-col gap-perto rounded-2xl bg-lavanda-clara p-5">
      <h3 id="titulo-excluir" className={TITULO_DE_SECAO}>
        Excluir minha conta
      </h3>

      {confirmando ? (
        <form onSubmit={aoConfirmar} noValidate aria-labelledby="aviso-excluir"
          className="flex flex-col gap-bloco">
          <p id="aviso-excluir" className="text-destaque font-bold">
            Isso apaga a sua conta e todo o seu histórico. Não dá para desfazer.
          </p>
          {/* Campo e avisos num grupo só: vazios, os avisos não abrem um buraco no espaçamento. */}
          <div className="flex flex-col gap-perto">
            <CampoSenha
              id="senha-exclusao"
              nome="senha-exclusao"
              rotulo="Sua senha"
              autoComplete="current-password"
              valor={senha}
              aoMudar={setSenha}
              somenteLeitura={enviando}
            />
            <AvisosDoEnvio demorando={demorando} erro={erro} avisoDeErro={avisoDeErro} />
          </div>
          {/* No celular, um botão por linha e na largura toda: "Sim, excluir minha conta" não
              quebra colado no "Cancelar". */}
          <div className="flex flex-col gap-junto sm:flex-row sm:flex-wrap">
            <button type="submit" disabled={enviando}
              className={`${BOTAO} botao-principal w-full sm:w-auto`}>
              {enviando ? "Excluindo…" : "Sim, excluir minha conta"}
            </button>
            <button type="button" ref={botaoCancelar} onClick={cancelar} disabled={enviando}
              className={`${BOTAO} botao-secundario w-full sm:w-auto`}>
              Cancelar
            </button>
          </div>
        </form>
      ) : (
        <>
          <p>Apaga a conta, as sessões abertas e todas as análises do histórico.</p>
          <button type="button" ref={botaoAbrir} onClick={abrir}
            className={`${BOTAO} botao-secundario self-start`}>
            Excluir minha conta
          </button>
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
