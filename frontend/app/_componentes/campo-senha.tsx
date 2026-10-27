"use client";

import { useState } from "react";

/** Campo de senha com botão de mostrar e ocultar.
 *
 *  O botão troca o próprio rótulo ("Mostrar" / "Ocultar") e não usa `aria-pressed`: com os dois
 *  juntos, o leitor de tela anunciaria "Ocultar senha, pressionado", que se contradiz. O rótulo
 *  que muda é também o que um usuário de baixo letramento digital entende sem ajuda. */
export function CampoSenha({
  id,
  autoComplete,
  valor,
  aoMudar,
  somenteLeitura,
  dica,
  rotulo = "Senha",
  nome = "senha",
}: {
  id: string;
  autoComplete: "current-password" | "new-password";
  valor: string;
  aoMudar: (valor: string) => void;
  somenteLeitura: boolean;
  /** Regra mostrada ANTES de qualquer erro, entre o rótulo e o campo. */
  dica?: string;
  /** "Senha atual" e "Nova senha" na troca de senha: dois campos no mesmo formulário. */
  rotulo?: string;
  /** `name` distinto por campo, para o gerenciador de senhas não confundir os dois. */
  nome?: string;
}) {
  const [visivel, setVisivel] = useState(false);
  const idDica = `${id}-dica`;

  return (
    <div className="flex flex-col gap-junto">
      <label htmlFor={id} className="font-bold">
        {rotulo}
      </label>
      {dica && <p id={idDica}>{dica}</p>}
      {/* Sem 9rem para o campo ao lado do botão, o botão desce: decide a largura do quadro, não
          a da tela (o mesmo campo fica estreito no quadro de exclusão e largo no de troca).
          `basis`, e não `min-w`: o `min-width` do `.alvo-de-toque`, fora de camada, venceria. */}
      <div className="flex flex-wrap items-stretch gap-2">
        <input
          id={id}
          name={nome}
          type={visivel ? "text" : "password"}
          autoComplete={autoComplete}
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          value={valor}
          onChange={(evento) => aoMudar(evento.target.value)}
          readOnly={somenteLeitura}
          aria-describedby={dica ? idDica : undefined}
          className="campo alvo-de-toque grow basis-[9rem] px-5 py-2 text-destaque"
        />
        <button
          type="button"
          onClick={() => setVisivel((atual) => !atual)}
          aria-controls={id}
          className="botao-secundario alvo-de-toque shrink-0 rounded-full px-4 font-bold"
        >
          {visivel ? "Ocultar" : "Mostrar"}
          {/* "Mostrar senha atual" e "Mostrar nova senha": dois botões, dois nomes distintos. */}
          <span className="sr-only"> {rotulo.toLocaleLowerCase("pt-BR")}</span>
        </button>
      </div>
    </div>
  );
}
