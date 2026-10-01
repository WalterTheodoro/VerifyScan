import Link from "next/link";

// NEXT_PUBLIC_ porque as páginas são geradas no build e o valor entra no HTML. Sem a variável, o
// aviso continua de pé e diz que o contato está em configuração.
const CONTATO = process.env.NEXT_PUBLIC_CONTATO_PRIVACIDADE?.trim() ?? "";

const LINK = "font-bold text-anil underline underline-offset-4 break-all";

/** Aviso de privacidade, em pt-BR simples, cobrindo o art. 9º da LGPD: quem é o responsável,
 *  para que, o que, por quanto tempo, onde, com quem e quais são os direitos.
 *
 *  O mesmo componente em /privacidade e em /conta/privacidade. O que está aqui precisa bater com
 *  o banco: models/, ADR-0006 e ADR-0015 (análise sem texto, vínculo de 7 dias), ADR-0013 (conta
 *  e sessão), ADR-0011 (Neon). `nivel` mantém a hierarquia de títulos de quem o usa. */
export function AvisoPrivacidade({ nivel }: { nivel: "h2" | "h3" }) {
  const Titulo = nivel;
  const titulo = "text-secao font-bold sm:text-secao-lg";

  return (
    <div className="flex flex-col gap-bloco text-destaque">
      <section aria-labelledby="quem" className="flex flex-col gap-junto">
        <Titulo id="quem" className={titulo}>Quem cuida dos seus dados</Titulo>
        <p>
          Walter Theodoro, estudante de Engenharia de Software da Católica SC. O VerifyScan é o
          trabalho de conclusão de curso dele.
        </p>
      </section>

      <section aria-labelledby="para-que" className="flex flex-col gap-junto">
        <Titulo id="para-que" className={titulo}>Para que usamos</Titulo>
        <p>
          Para você entrar na sua conta e ver o histórico das suas análises. A análise em si
          funciona sem conta.
        </p>
      </section>

      <section aria-labelledby="com-conta" className="flex flex-col gap-junto">
        <Titulo id="com-conta" className={titulo}>Se você criar uma conta, guardamos</Titulo>
        <ul className="flex list-disc flex-col gap-junto pl-6">
          <li>o nome que você escolheu para ser chamado;</li>
          <li>o seu e-mail;</li>
          <li>
            a sua senha, mas só embaralhada de um jeito que não dá para desfazer (uma técnica
            chamada Argon2id). Nem nós conseguimos ver a sua senha;
          </li>
          <li>
            uma sessão que mantém você conectado neste navegador por até 7 dias. Ao tocar em
            &ldquo;Sair&rdquo;, ela é apagada.
          </li>
        </ul>
      </section>

      <section aria-labelledby="analises" className="flex flex-col gap-junto">
        <Titulo id="analises" className={titulo}>Das análises, guardamos</Titulo>
        <p>
          Só o nível de risco, a pontuação, os sinais encontrados e a data.{" "}
          <strong>Nunca o texto da mensagem que você colou.</strong>
        </p>
        <p>
          As análises feitas com a conta aberta ficam ligadas a ela por 7 dias, para aparecer no
          seu histórico. Depois disso, deixam de ficar ligadas a você.
        </p>
      </section>

      <section aria-labelledby="tempo" className="flex flex-col gap-junto">
        <Titulo id="tempo" className={titulo}>Por quanto tempo</Titulo>
        <ul className="flex list-disc flex-col gap-junto pl-6">
          <li>a conta, até você pedir para apagar;</li>
          <li>a ligação das análises com a sua conta, 7 dias.</li>
        </ul>
      </section>

      <section aria-labelledby="acessos" className="flex flex-col gap-junto">
        <Titulo id="acessos" className={titulo}>Registros de acesso</Titulo>
        <p>
          A Render, empresa onde o site roda, guarda por um tempo limitado registros com o
          endereço IP e o horário de cada acesso. Eles servem para o site funcionar.
        </p>
      </section>

      <section aria-labelledby="onde" className="flex flex-col gap-junto">
        <Titulo id="onde" className={titulo}>Onde ficam e com quem</Titulo>
        <p>
          Em servidores nos Estados Unidos, de duas empresas: a Render, onde o site roda, e a
          Neon, onde fica o banco de dados. Elas só guardam e rodam o sistema. Não vendemos nem
          repassamos os seus dados a mais ninguém.
        </p>
      </section>

      <section aria-labelledby="direitos" className="flex flex-col gap-junto">
        <Titulo id="direitos" className={titulo}>Os seus direitos</Titulo>
        <ul className="flex list-disc flex-col gap-junto pl-6">
          <li>
            ver o seu histórico, em{" "}
            <Link href="/conta/historico" className={LINK}>Minha conta</Link>;
          </li>
          <li>apagar uma análise ou todas, no próprio histórico;</li>
          <li>
            pedir para apagar a sua conta e os seus dados:{" "}
            {CONTATO ? (
              <>
                escreva para{" "}
                <a href={`mailto:${CONTATO}`} className={LINK}>
                  {CONTATO}
                </a>
                .
              </>
            ) : (
              <>escreva para o nosso contato, que está em configuração.</>
            )}
          </li>
        </ul>
      </section>
    </div>
  );
}
