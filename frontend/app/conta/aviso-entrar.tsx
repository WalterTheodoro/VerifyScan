import Link from "next/link";

/** O que o painel mostra sem sessão (401). Sem redirecionar: quem chegou por um link entende
 *  onde está, e a URL continua a mesma depois de entrar e voltar (ADR-0016). */
export function AvisoEntrar() {
  return (
    <div className="flex flex-col gap-perto">
      <p className="text-destaque">Entre na sua conta para ver esta página.</p>
      <Link
        href="/entrar"
        className="botao-principal alvo-de-toque inline-flex items-center justify-center
          self-start rounded-full px-8 font-bold"
      >
        Entrar
      </Link>
    </div>
  );
}
