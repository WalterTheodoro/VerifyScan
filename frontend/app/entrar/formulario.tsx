"use client";

import Link from "next/link";
import { useState } from "react";

import { AvisosDoEnvio } from "../_componentes/avisos-do-envio";
import { CampoSenha } from "../_componentes/campo-senha";
import { useEnvioConta } from "../_lib/use-envio-conta";

export function FormularioEntrar() {
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const { enviando, demorando, erro, avisoDeErro, enviar } = useEnvioConta("/api/auth/login");

  function aoEnviar(evento: React.FormEvent) {
    evento.preventDefault();
    enviar({ email, senha });
  }

  return (
    // `noValidate`: quem valida é o backend, que já responde em pt-BR (ADR-0013). O balão
    // nativo do navegador viria antes, com outra redação.
    <form onSubmit={aoEnviar} noValidate className="cartao flex flex-col gap-bloco p-5 sm:p-bloco">
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
          className="campo alvo-de-toque w-full px-5 py-2 text-destaque"
        />
      </div>

      <CampoSenha
        id="senha"
        autoComplete="current-password"
        valor={senha}
        aoMudar={setSenha}
        somenteLeitura={enviando}
      />

      <AvisosDoEnvio demorando={demorando} erro={erro} avisoDeErro={avisoDeErro} />

      <button
        type="submit"
        disabled={enviando}
        className="botao-principal alvo-de-toque w-full rounded-full px-8 py-3 text-destaque
          font-bold"
      >
        {enviando ? "Entrando…" : "Entrar"}
      </button>

      <p>
        Ainda não tem conta?{" "}
        <Link href="/cadastro" className="font-bold text-anil underline underline-offset-4">
          Criar conta
        </Link>
      </p>
    </form>
  );
}
