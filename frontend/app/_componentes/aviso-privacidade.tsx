import Link from "next/link";

// NEXT_PUBLIC_ porque as páginas são geradas no build e o valor entra no HTML. Sem a variável, o
// aviso continua de pé e diz que o contato está em configuração.
const CONTATO = process.env.NEXT_PUBLIC_CONTATO_PRIVACIDADE?.trim() ?? "";

const LINK = "font-bold text-anil underline underline-offset-4 break-all";

/** Aviso de privacidade, em pt-BR simples, cobrindo o art. 9º da LGPD: quem é o responsável,
 *  para que, o que, por quanto tempo, onde, com quem e quais são os direitos.
 *
 *  O mesmo componente em /privacidade e em /conta/privacidade. O que está aqui precisa bater com
 *  o banco: models/, ADR-0006 e ADR-0015 (anônima sem texto, vínculo de 7 dias), ADR-0018 (a
 *  mensagem de quem tem conta, pelos mesmos 7 dias), ADR-0013 e ADR-0019 (conta, sessão e
 *  exclusão), ADR-0011 (Neon), ADR-0020 (a mensagem vai à Anthropic; o que a IA escreveu segue a
 *  regra da mensagem), ADR-0023 (o print vai à Anthropic só para ser lido e nunca é guardado; do
 *  print, fica o texto lido e o contexto, com a regra da mensagem). `nivel` mantém a hierarquia
 *  de títulos de quem o usa. */
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
          Para analisar a mensagem que você colou, ou o print que você enviou, e dizer o que
          fazer. A análise funciona sem conta.
        </p>
        <p>
          Se você criar uma conta, também para você entrar nela e ver o histórico das suas
          análises, com a mensagem que você analisou.
        </p>
      </section>

      <section aria-labelledby="ia" className="flex flex-col gap-junto">
        <Titulo id="ia" className={titulo}>A análise com inteligência artificial</Titulo>
        <p>
          Para dizer o que a mensagem parece ser e o que fazer, enviamos o texto que você colou,
          ou o print que você enviou, à Anthropic, a empresa que faz a inteligência artificial
          Claude.{" "}
          <strong>Isso vale com ou sem conta.</strong>
        </p>
        <p>
          Vão só a mensagem, os sinais que as nossas regras encontraram nela e os links que ela
          tem. Não vão o seu nome, o seu e-mail nem nada da sua conta.
        </p>
        <p>
          Pelas regras da Anthropic para empresas que usam a inteligência artificial dela, ela
          não usa esse conteúdo para treinar os seus modelos e o apaga em até 30 dias. Ela pode
          guardar por mais tempo, até 2 anos, o que os sistemas dela marcarem como violação das
          suas regras de uso, e também o que a lei exigir.
        </p>
        <p>
          A Anthropic fica nos Estados Unidos. Enviar a mensagem para ela é, por isso, uma
          transferência internacional de dados (Lei Geral de Proteção de Dados, art. 33).
        </p>
        <p>
          Se a inteligência artificial não responder, a análise sai só com as nossas regras.
        </p>
      </section>

      <section aria-labelledby="print" className="flex flex-col gap-junto">
        <Titulo id="print" className={titulo}>Se você enviar um print</Titulo>
        <p>
          O print pode mostrar o nome, o número e a foto de outras pessoas, além da mensagem. Se
          der, recorte o que não for a mensagem antes de enviar.
        </p>
        <p>
          Antes de sair do seu aparelho, o próprio navegador diminui a imagem e tira os dados
          escondidos nela, como o lugar onde a foto foi tirada.
        </p>
        <p>
          A imagem vai para a Anthropic, nos Estados Unidos, só para a inteligência artificial ler
          o texto dela, com as mesmas regras da mensagem explicadas acima.
        </p>
        <p>
          <strong>
            O VerifyScan nunca guarda a imagem: nem no banco de dados, nem em arquivo, nem nos
            registros do sistema.
          </strong>{" "}
          Com a conta aberta, guardamos só o texto que lemos do print e o que ele mostrava em
          volta da mensagem (por exemplo, se quem mandou está nos seus contatos), pelos mesmos 7
          dias da mensagem.
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
          O nível de risco, a pontuação, os sinais encontrados, o nível que a inteligência
          artificial sugeriu e a data.
        </p>
        <p>
          <strong>
            Sem conta, nunca guardamos o texto da mensagem que você colou, nem o que lemos do
            print.
          </strong>
        </p>
        <p>
          Com a conta aberta, guardamos também a mensagem (ou o texto lido do print, com o que
          ele mostrava em volta) e o que a inteligência artificial escreveu sobre ela, para
          aparecerem no seu histórico. Isso faz parte do
          histórico que você usa ao criar a conta, e a tela de análise avisa antes de enviar.
          Depois de 7 dias, os dois são apagados e a análise deixa de ficar ligada a você. Você
          pode apagá-la antes, a qualquer momento.
        </p>
        <p>
          A mensagem pode ter dados de outras pessoas, como o nome ou o telefone de quem a
          enviou. Por isso ela fica só esses 7 dias.
        </p>
      </section>

      <section aria-labelledby="tempo" className="flex flex-col gap-junto">
        <Titulo id="tempo" className={titulo}>Por quanto tempo</Titulo>
        <ul className="flex list-disc flex-col gap-junto pl-6">
          <li>a conta, até você excluí-la;</li>
          <li>
            a mensagem que você analisou com a conta aberta, e o que a inteligência artificial
            escreveu sobre ela, 7 dias;
          </li>
          <li>na Anthropic, a mensagem ou o print enviado para a análise, até 30 dias;</li>
          <li>no VerifyScan, a imagem do print: não é guardada;</li>
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
          Em servidores nos Estados Unidos, de três empresas: a Render, onde o site roda; a
          Neon, onde fica o banco de dados; e a Anthropic, que faz a análise com inteligência
          artificial, como explicado acima. Não vendemos nem repassamos os seus dados a mais
          ninguém.
        </p>
      </section>

      <section aria-labelledby="direitos" className="flex flex-col gap-junto">
        <Titulo id="direitos" className={titulo}>Os seus direitos</Titulo>
        <ul className="flex list-disc flex-col gap-junto pl-6">
          <li>
            ver o seu histórico, em{" "}
            <Link href="/conta/historico" className={LINK}>Minha conta</Link>;
          </li>
          <li>apagar uma análise ou todas, com a mensagem, no próprio histórico;</li>
          <li>
            excluir a sua conta e todo o histórico, em{" "}
            <Link href="/conta/dados" className={LINK}>Minha conta → Meus dados</Link>;
          </li>
          <li>
            ou pedir para apagar a sua conta e os seus dados:{" "}
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
