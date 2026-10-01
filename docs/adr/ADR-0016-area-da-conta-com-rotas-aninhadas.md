# ADR-0016 — Área da conta com rotas aninhadas

**Data:** 2026-10-01 · **Status:** aceito · **Fase:** 8 (fatia 4)

## Contexto

A conta ganha três seções: Histórico, Meus dados e Privacidade. A fatia 5 acrescenta trocar a senha
e excluir a conta. O público tem baixo letramento digital, usa o botão voltar do celular como
principal forma de navegar e, muitas vezes, divide o aparelho com a família. O cabeçalho já foi
medido no limite em 320 px (fatia 3).

## Opções consideradas

- **Abas em JavaScript** numa página só, com o padrão ARIA `tablist`.
- **Menu suspenso** no cabeçalho, com os itens da conta.
- **Rotas aninhadas com layout** (`app/conta/layout.tsx`), uma URL por seção.

## Decisão

**Rotas aninhadas com layout.**
- `/conta/historico`, `/conta/dados` e `/conta/privacidade` têm URL própria.
- `/conta` redireciona para `/conta/historico` com um 307 de servidor (`redirects()` no
  `next.config.ts`). Com `redirect()` numa página, a rota seria pré-renderizada estática e
  dependeria do JavaScript: medido, aberta direto, ela ficava em `/conta`.
- O layout guarda a moldura: cabeçalho, título "Minha conta", menu, painel e rodapé. Ao trocar de
  seção, só o painel muda, e a sessão é consultada uma vez ao entrar na área.
- O menu usa links dentro de `<nav aria-label="Minha conta">`, com `aria-current="page"` no item
  atual.
  - **Não** usa o padrão ARIA de abas: abas trocam de painel sem trocar de página, e aqui cada item
    é uma página.
  - O voltar do navegador funciona sem código.
- **O cabeçalho não ganha item novo.** "Olá, {nome}" vira um link com visual de botão para `/conta`.
- Deslogado, o painel mostra "Entre na sua conta para ver esta página.", sem redirecionar: a URL
  continua a mesma depois de entrar e voltar.

Medido no build de produção, nas larguras 320, 375, 390, 640, 768, 1024 e 1280 px, deslogado e com
um nome de 60 caracteres:
- o cabeçalho mantém as alturas da fatia 3: 165, 116 e 68 px;
- não há rolagem lateral, sobreposição nem alvo abaixo de 44 px;
- os três rótulos do menu cabem inteiros em 320 px, com 133 px por coluna.

## Custo de estar errado

- **Abas em JS:** sem URL por seção, o voltar sairia da conta inteira, e o link "veja a seção
  Privacidade" não teria destino. O padrão `tablist` também exige setas e foco gerenciado, que
  confundem quem não conhece abas.
- **Menu suspenso:** um item a mais num cabeçalho que já chega a 165 px em 320 px, e um controle
  que abre e fecha, mais difícil de achar para o público.
- **O custo da escolha feita:** cada seção é uma navegação. No plano gratuito, a primeira pode
  esperar o servidor acordar, e a tela avisa depois de 5 s. Se as seções crescerem demais para o
  menu em duas colunas no celular, a grade muda; as URLs ficam.
