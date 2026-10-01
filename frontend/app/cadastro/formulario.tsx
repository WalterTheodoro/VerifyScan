"use client";

import Link from "next/link";
import { useState } from "react";

import { AvisosDoEnvio } from "../_componentes/avisos-do-envio";
import { CampoSenha } from "../_componentes/campo-senha";
import { useEnvioConta } from "../_lib/use-envio-conta";

const CAMPO = "campo alvo-de-toque w-full px-5 py-2 text-destaque";

export function FormularioCadastro() {
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const { enviando, demorando, erro, avisoDeErro, enviar } = useEnvioConta("/api/auth/cadastro");

  function aoEnviar(evento: React.FormEvent) {
    evento.preventDefault();
    enviar({ nome, email, senha });
  }

  return (
    // `noValidate`: quem valida é o backend, que já responde em pt-BR (ADR-0013). O balão
    // nativo do navegador viria antes, com outra redação.
    <form onSubmit={aoEnviar} noValidate className="cartao flex flex-col gap-bloco p-5 sm:p-bloco">
      <div className="flex flex-col gap-junto">
        <label htmlFor="nome" className="font-bold">
          Como quer ser chamado?
        </label>
        <input
          id="nome"
          name="nome"
          type="text"
          autoComplete="name"
          value={nome}
          onChange={(evento) => setNome(evento.target.value)}
          readOnly={enviando}
          className={CAMPO}
        />
      </div>

      <div className="flex flex-col gap-junto">
        <label htmlFor="email" className="font-bold">
          E-mail
        </label>
        <input
          id="email"
          name="email"
          type="email"
          inputMode="email"
          autoComplete="email"
          autoCapitalize="none"
          spellCheck={false}
          value={email}
          onChange={(evento) => setEmail(evento.target.value)}
          readOnly={enviando}
          className={CAMPO}
        />
      </div>

      {/* A regra vem antes de qualquer erro. O número é o mesmo do backend (ADR-0013 §5). */}
      <CampoSenha
        id="senha"
        autoComplete="new-password"
        valor={senha}
        aoMudar={setSenha}
        somenteLeitura={enviando}
        dica="Use pelo menos 8 caracteres."
      />

      <AvisosDoEnvio demorando={demorando} erro={erro} avisoDeErro={avisoDeErro} />

      <div className="flex flex-col gap-perto">
        <button
          type="submit"
          disabled={enviando}
          className="botao-principal alvo-de-toque w-full rounded-full px-8 py-3 text-destaque
            font-bold"
        >
          {enviando ? "Criando conta…" : "Criar conta"}
        </button>
        <p>
          Ao criar a conta, você concorda com o{" "}
          <Link href="/privacidade" className="font-bold text-anil underline underline-offset-4">
            aviso de privacidade
          </Link>
          .
        </p>
      </div>

      <p>
        Já tem conta?{" "}
        <Link href="/entrar" className="font-bold text-anil underline underline-offset-4">
          Entrar
        </Link>
      </p>
    </form>
  );
}
