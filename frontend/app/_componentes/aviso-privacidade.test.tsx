// @vitest-environment jsdom
// O aviso de privacidade só fala do aviso de erro quando o Sentry está ligado (ADR-0026): o texto
// tem de dizer a verdade com e sem a variável.
//
//   npm test

import assert from "node:assert/strict";
import { render, screen } from "@testing-library/react";
import { afterEach, test, vi } from "vitest";

// O componente lê a variável quando o módulo carrega, como no build.
async function carregar() {
  vi.resetModules();
  return (await import("./aviso-privacidade")).AvisoPrivacidade;
}

afterEach(() => {
  vi.unstubAllEnvs();
});

test("sem o Sentry, não há seção sobre erros", async () => {
  vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "");
  const AvisoPrivacidade = await carregar();

  render(<AvisoPrivacidade nivel="h2" />);

  assert.equal(screen.queryByRole("heading", { name: TITULO }), null);
  assert.equal(screen.queryByText(/Sentry/), null);
});

const TITULO = "Avisos de erro e de desempenho";

/** O texto da seção, numa linha só: o JSX quebra as frases em várias linhas. */
function textoDaSecao(): string {
  const secao = screen.getByRole("heading", { name: TITULO }).closest("section");
  assert.ok(secao);
  return (secao.textContent ?? "").replace(/\s+/g, " ");
}

test("com o Sentry, diz o que vai, quando vai e o que nunca vai", async () => {
  vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "https://chave@o0.ingest.exemplo.invalid/1");
  const AvisoPrivacidade = await carregar();

  render(<AvisoPrivacidade nivel="h2" />);

  assert.ok(screen.getByRole("heading", { level: 2, name: TITULO }));
  const texto = textoDaSecao();
  // Os erros: do site e do servidor, e o que o aviso diz.
  assert.match(texto, /no site ou no servidor/);
  assert.match(texto, /que tipo de erro foi e qual navegador você usa/);
  // O desempenho vai SEM erro nenhum, numa parte das visitas: o aviso tem de dizer isso.
  assert.match(texto, /1 a cada 10 visitas/);
  assert.match(texto, /o endereço da página, só o caminho/);
  assert.match(texto, /quanto tempo a página levou para carregar/);
  // O idioma e o fuso não vão mais (a integração foi desligada): o aviso não pode citá-los.
  assert.doesNotMatch(texto, /idioma|fuso/);
  // O que nunca vai.
  assert.match(
    texto,
    /Nunca vão a mensagem que você colou, o print, o seu e-mail, a sua senha, o endereço IP da sua conexão nem o que você digita/,
  );
  assert.match(texto, /Não gravamos a sua tela/);
  // Onde ficam: o país, não "fora do Brasil", e que é transferência internacional.
  assert.match(texto, /servidores da Sentry ficam nos Estados Unidos/);
  assert.match(texto, /transferência internacional de dados/);
  assert.doesNotMatch(texto, /fora do Brasil/);
  // E a lista de com quem os dados ficam passa a citar a Sentry.
  assert.ok(screen.getByText(/Os avisos de erro e as medidas de desempenho vão para a Sentry/));
});

/** O texto de uma seção pelo título, numa linha só. */
function textoDe(titulo: string): string {
  const secao = screen.getByRole("heading", { name: titulo }).closest("section");
  assert.ok(secao);
  return (secao.textContent ?? "").replace(/\s+/g, " ");
}

// Onde os dados ficam depende de onde o site roda (ADR-0029). Enquanto o Render e a VM da Azure
// estão no ar ao mesmo tempo, cada um tem de dizer a verdade sobre si: quem decide é a variável
// que só o build da imagem define.
test("na Azure, diz que a conta e o histórico ficam no Chile e o que isso significa", async () => {
  vi.stubEnv("NEXT_PUBLIC_HOSPEDAGEM", "azure");
  vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "");
  const AvisoPrivacidade = await carregar();

  const { container } = render(<AvisoPrivacidade nivel="h2" />);

  const onde = textoDe("Onde ficam e com quem");
  assert.match(onde, /servidor da Microsoft Azure, no Chile/);
  assert.match(onde, /a sua conta e o seu histórico/);
  // O país pelo nome, e que é transferência internacional, com o artigo da lei.
  assert.match(
    onde,
    /transferência internacional de dados \(Lei Geral de Proteção de Dados, art\. 33\)/,
  );
  assert.doesNotMatch(onde, /fora do Brasil/);
  // Quem recebe a mensagem continua dito.
  assert.match(onde, /Anthropic, nos Estados Unidos/);
  assert.match(onde, /Google e ao VirusTotal/);
  // A cópia de segurança guarda por 7 dias o que a pessoa apagou: o aviso tem de dizer.
  assert.match(onde, /cópia de segurança do banco de dados/);
  assert.match(textoDe("Por quanto tempo"), /cópias de segurança[^;]*7 dias/);
  // Na VM não há registro de acesso com IP (invariante 2).
  assert.match(textoDe("Registros de acesso"), /não guarda registros com o endereço IP/);
  // E nada do que valia só no Render.
  assert.doesNotMatch(container.textContent ?? "", /Render|Neon/);
});

test("fora da Azure, o aviso continua o do Render e da Neon", async () => {
  vi.stubEnv("NEXT_PUBLIC_HOSPEDAGEM", "");
  vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "");
  const AvisoPrivacidade = await carregar();

  const { container } = render(<AvisoPrivacidade nivel="h2" />);

  const onde = textoDe("Onde ficam e com quem");
  assert.match(onde, /a Render, onde o site roda/);
  assert.match(onde, /a Neon, onde fica o banco de dados/);
  assert.match(textoDe("Registros de acesso"), /A Render, empresa onde o site roda/);
  assert.doesNotMatch(container.textContent ?? "", /Azure|Chile|cópia de segurança/);
});

test("o nível dos títulos acompanha a página", async () => {
  vi.stubEnv("NEXT_PUBLIC_SENTRY_DSN", "");
  const AvisoPrivacidade = await carregar();

  render(<AvisoPrivacidade nivel="h3" />);

  assert.ok(screen.getByRole("heading", { level: 3, name: "Quem cuida dos seus dados" }));
  assert.equal(screen.queryAllByRole("heading", { level: 2 }).length, 0);
});
