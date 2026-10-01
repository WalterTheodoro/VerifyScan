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
}: {
  id: string;
  autoComplete: "current-password" | "new-password";
  valor: string;
  aoMudar: (valor: string) => void;
  somenteLeitura: boolean;
  /** Regra mostrada ANTES de qualquer erro, entre o rótulo e o campo. */
  dica?: string;
}) {
  const [visivel, setVisivel] = useState(false);
  const idDica = `${id}-dica`;

  return (
    <div className="flex flex-col gap-junto">
      <label htmlFor={id} className="font-bold">
        Senha
      </label>
      {dica && <p id={idDica}>{dica}</p>}
      <div className="flex items-stretch gap-2">
        <input
          id={id}
          name="senha"
          type={visivel ? "text" : "password"}
          autoComplete={autoComplete}
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          value={valor}
          onChange={(evento) => aoMudar(evento.target.value)}
          readOnly={somenteLeitura}
          aria-describedby={dica ? idDica : undefined}
          className="campo alvo-de-toque min-w-0 flex-1 px-5 py-2 text-destaque"
        />
        <button
          type="button"
          onClick={() => setVisivel((atual) => !atual)}
          aria-controls={id}
          className="botao-secundario alvo-de-toque shrink-0 rounded-full px-4 font-bold"
        >
          {visivel ? "Ocultar" : "Mostrar"}
          <span className="sr-only"> senha</span>
        </button>
      </div>
    </div>
  );
}
