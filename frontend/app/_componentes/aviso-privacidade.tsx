import Link from "next/link";

// NEXT_PUBLIC_ porque as páginas são geradas no build e o valor entra no HTML. Sem a variável, o
// aviso continua de pé e diz que o contato está em configuração.
const CONTATO = process.env.NEXT_PUBLIC_CONTATO_PRIVACIDADE?.trim() ?? "";
// A mesma variável que liga o Sentry (ADR-0026): sem ela, nenhum aviso de erro sai do site, e a
// seção sobre isso não aparece. Também lida no build.
const AVISA_ERROS = Boolean(process.env.NEXT_PUBLIC_SENTRY_DSN?.trim());
// Onde o site roda (ADR-0029). Só o build da imagem (frontend/Dockerfile) define "azure". Enquanto
// o Render e a VM da Azure estão no ar ao mesmo tempo, cada um mostra o aviso verdadeiro para si;
// depois do corte, o ramo do Render e esta variável saem.
const NA_AZURE = process.env.NEXT_PUBLIC_HOSPEDAGEM?.trim() === "azure";

const LINK = "font-bold text-anil underline underline-offset-4 break-all";

/** Aviso de privacidade, em pt-BR simples, cobrindo o art. 9º da LGPD: quem é o responsável,
 *  para que, o que, por quanto tempo, onde, com quem e quais são os direitos.
 *
 *  O mesmo componente em /privacidade e em /conta/privacidade. O que está aqui precisa bater com
 *  o banco: models/, ADR-0006 e ADR-0015 (anônima sem texto, vínculo de 7 dias), ADR-0018 (a
 *  mensagem de quem tem conta, pelos mesmos 7 dias), ADR-0013 e ADR-0019 (conta, sessão e
 *  exclusão), ADR-0011 (Neon, no Render) e ADR-0029 (na Azure: a VM no Chile, sem registro de
 *  acesso com IP, e a cópia de segurança diária por 7 dias), ADR-0020 (a mensagem vai à
 *  Anthropic; o que a IA escreveu segue a
 *  regra da mensagem), ADR-0023 (o print vai à Anthropic só para ser lido e nunca é guardado; do
 *  print, fica o texto lido e o contexto, com a regra da mensagem), ADR-0024 (a contagem diária
 *  da IA e dos cadastros, pelo HMAC do IP ou pela conta, 2 dias; senhas erradas só em memória),
 *  ADR-0026 (o aviso de erro, do site e do servidor, e as medidas de desempenho de ~10% das
 *  visitas vão à Sentry, nos EUA, sem conteúdo, sem conta e sem IP; nenhum lado manda contagem
 *  de sessões, e o navegador não manda idioma e fuso; a tela não é gravada).
 *  `nivel` mantém a hierarquia de títulos de quem o usa. */
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
          Se a inteligência artificial não responder, ou se as análises com ela já tiverem
          acabado no dia, a análise sai só com as nossas regras.
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
          histórico que você usa ao criar a conta, e a página de análise avisa disso.
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
          <li>
            a resposta das bases externas sobre um domínio, até 24 horas, sem o domínio escrito;
          </li>
          <li>no VirusTotal, o domínio consultado: fica na base dele, sem prazo nosso;</li>
          <li>no VerifyScan, a imagem do print: não é guardada;</li>
          <li>a ligação das análises com a sua conta, 7 dias;</li>
          <li>
            a contagem diária das análises com inteligência artificial e das contas criadas, 2
            dias;
          </li>
          <li>
            a contagem de senhas erradas, 15 minutos, só na memória do servidor
            {NA_AZURE ? ";" : "."}
          </li>
          {NA_AZURE && (
            <li>
              as cópias de segurança do banco de dados, 7 dias: o que você apagar some delas em
              até 7 dias.
            </li>
          )}
        </ul>
      </section>

      <section aria-labelledby="limites" className="flex flex-col gap-junto">
        <Titulo id="limites" className={titulo}>Limite de análises e proteção da conta</Titulo>
        <p>
          Cada análise com inteligência artificial tem um custo. Para ninguém gastar sozinho o que
          é de todos, contamos quantas análises com ela cada pessoa fez no dia. Pelo mesmo motivo,
          contamos as contas criadas a partir de cada conexão no dia.
        </p>
        <p>
          Com a conta aberta, a contagem fica ligada à sua conta. Sem conta, ela fica ligada a um
          código feito a partir do endereço IP da sua conexão com uma chave secreta do VerifyScan.{" "}
          <strong>O endereço IP não é guardado.</strong> Sem a chave, não dá para voltar do código
          ao endereço; mesmo assim, o código continua sendo um dado sobre você.
        </p>
        <p>
          Guardamos só o código (ou a conta), o dia e quantas análises foram feitas. Nunca a
          mensagem, nem a hora de cada análise. A contagem é apagada depois de 2 dias, e a de uma
          conta sai junto quando ela é excluída.
        </p>
        <p>
          Para proteger as contas de quem tenta adivinhar senhas, também contamos as senhas
          erradas, por 15 minutos. Essa contagem fica só na memória do servidor e some quando ele
          reinicia.
        </p>
        <p>
          Fazemos isso para evitar abuso, o que a Lei Geral de Proteção de Dados permite como
          interesse legítimo (art. 7º, inciso IX), usando só o necessário (art. 10, § 1º).
        </p>
      </section>

      <section aria-labelledby="acessos" className="flex flex-col gap-junto">
        <Titulo id="acessos" className={titulo}>Registros de acesso</Titulo>
        {NA_AZURE ? (
          <p>
            O VerifyScan não guarda registros com o endereço IP de quem acessa o site. A
            Microsoft, dona do servidor onde o site roda, pode registrar dados técnicos da conexão
            para manter a rede dela funcionando.
          </p>
        ) : (
          <p>
            A Render, empresa onde o site roda, guarda por um tempo limitado registros com o
            endereço IP e o horário de cada acesso. Eles servem para o site funcionar.
          </p>
        )}
      </section>

      {AVISA_ERROS && (
        <section aria-labelledby="erros" className="flex flex-col gap-junto">
          <Titulo id="erros" className={titulo}>Avisos de erro e de desempenho</Titulo>
          <p>
            Usamos a Sentry, uma empresa que ajuda a encontrar defeitos em programas. Ela recebe
            dois tipos de aviso técnico:
          </p>
          <ul className="flex list-disc flex-col gap-junto pl-6">
            <li>
              <strong>quando alguma coisa quebra</strong>, no site ou no servidor: em que página o
              erro aconteceu, em que parte do programa, que tipo de erro foi e qual navegador você
              usa;
            </li>
            <li>
              <strong>medidas de desempenho</strong>, em cerca de 1 a cada 10 visitas, mesmo sem
              erro: o endereço da página, só o caminho (como /privacidade), o navegador e quanto
              tempo a página levou para carregar.
            </li>
          </ul>
          <p>
            <strong>
              Nunca vão a mensagem que você colou, o print, o seu e-mail, a sua senha, o endereço
              IP da sua conexão nem o que você digita.
            </strong>{" "}
            Não gravamos a sua tela. Os avisos do site passam primeiro pelo nosso servidor, que os
            repassa sem o seu endereço IP.
          </p>
          <p>
            Os servidores da Sentry ficam nos Estados Unidos. Enviar os avisos para ela é, por
            isso, uma transferência internacional de dados (Lei Geral de Proteção de Dados, art.
            33).
          </p>
        </section>
      )}

      <section aria-labelledby="links" className="flex flex-col gap-junto">
        <Titulo id="links" className={titulo}>A consulta dos links em bases externas</Titulo>
        <p>
          Quando a mensagem tem link, perguntamos a duas bases externas se o endereço dele
          já foi apontado como perigoso: o Google Safe Browsing e o VirusTotal.{" "}
          <strong>Isso vale com ou sem conta.</strong>
        </p>
        <p>
          Vai só o domínio do link, que é o nome do site (por exemplo,{" "}
          <span className="font-mono">exemplo.com.br</span>). Não vão o resto do link, a
          mensagem, o seu nome, o seu e-mail nem nada da sua conta. Consultamos no máximo três
          domínios por análise, e nunca abrimos o link.
        </p>
        <p>
          <strong>
            O domínio consultado no VirusTotal passa a constar na base dele, que é visível às
            pessoas e empresas que a usam, e o VirusTotal pode visitar esse endereço para
            examiná-lo.
          </strong>{" "}
          Ele não fica sabendo quem pediu a análise.
        </p>
        <p>
          As duas empresas ficam nos Estados Unidos. Guardamos a resposta delas por até 24
          horas, para não repetir a pergunta, sem o domínio escrito: só um código calculado a
          partir dele.
        </p>
        <p>
          Se as bases não responderem, a análise sai só com as nossas regras, e a tela avisa.
        </p>
      </section>

      <section aria-labelledby="onde" className="flex flex-col gap-junto">
        <Titulo id="onde" className={titulo}>Onde ficam e com quem</Titulo>
        {NA_AZURE && (
          <p>
            O site e o banco de dados ficam em um servidor da Microsoft Azure, no Chile. É lá que
            ficam a sua conta e o seu histórico. Como o servidor fica no Chile, guardar esses
            dados lá é uma transferência internacional de dados (Lei Geral de Proteção de Dados,
            art. 33). Todo dia é feita uma cópia de segurança do banco de dados, que fica no mesmo
            lugar por 7 dias.
          </p>
        )}
        <p>
          {NA_AZURE ? (
            <>
              A análise com inteligência artificial é feita pela Anthropic, nos Estados Unidos,
              como explicado acima.
            </>
          ) : (
            <>
              Em servidores nos Estados Unidos, de três empresas: a Render, onde o site roda; a
              Neon, onde fica o banco de dados; e a Anthropic, que faz a análise com inteligência
              artificial, como explicado acima.
            </>
          )}{" "}
          O domínio dos links vai também ao Google e ao VirusTotal, nos Estados Unidos, como
          explicado acima.
          {AVISA_ERROS && (
            <>
              {" "}
              Os avisos de erro e as medidas de desempenho vão para a Sentry, também como
              explicado acima.
            </>
          )}{" "}
          Não vendemos nem repassamos os seus dados a mais ninguém.
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
