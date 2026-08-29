# ADR-0010 — Interface: acessibilidade e feedback de progresso

**Data:** 2026-08-29 · **Status:** aceito · **Fases:** 1, 5, 9

## Contexto

O público-alvo do RFC inclui idosos e pessoas com baixo letramento digital. Isso torna a interface
parte do requisito, não acabamento: uma resposta correta que a pessoa não consegue ler é uma
resposta errada. O RNF05 pede design responsivo e é tudo o que o documento diz sobre a questão.

Há ainda uma divergência a reconciliar. A "Tela 2 — Análise em Andamento" (§4.2, p. 14) descreve
etapas com vocabulário do sistema — "Extraindo URLs…", "Verificando domínios…" — e uma barra de
progresso percentual. Na Fase 1 a análise leva menos de um segundo e a tela não se justifica; e o
vocabulário contraria a regra de não expor jargão ao usuário.

## Opções consideradas

- **Nível de risco:** destaque por cor, como no mockup × **cor, ícone e palavra sempre juntos**.
- **Tema:** claro e escuro × **claro fixo na Fase 1**.
- **Tela de progresso:** manter como no RFC × cortar de vez × **reintroduzir quando a espera
  existir, em vocabulário do usuário**.
- **Resultado:** rota `/resultado` própria × **estado da mesma página**.

## Decisão

**1. O nível de risco nunca é comunicado só por cor.** Sempre cor + ícone + palavra ("Risco alto"
por extenso). Vale para qualquer estado futuro que a interface venha a ter.

**2. Piso de acessibilidade da Fase 1**, verificado em cada tela:
fonte base **18px** · contraste mínimo **AA** (4,5:1 para texto normal) · alvo de toque mínimo
**44px** (WCAG 2.5.5) · foco sempre visível · resultado anunciado por `aria-live` e foco levado
para o título quando ele chega · **nenhum jargão técnico visível** ("Fatores identificados", não
"heurísticas detectadas").

**3. Tema claro fixo na Fase 1.** Tema escuro, se entrar, é da Fase 9.

**4. Progresso, por fase:**

| Fase | O que a tela mostra durante a análise |
|---|---|
| 1 | Estado único: "Analisando sua mensagem…" |
| 5 em diante | As etapas do RFC voltam, **em vocabulário do usuário**: "Lendo a imagem…", "Conferindo o endereço do site…", "Procurando sinais de golpe…" |
| nenhuma | **A barra de progresso percentual do mockup não volta.** |

**5. Resultado é estado da mesma página**, não rota própria.

## Consequências

- **Cor sozinha exclui parte do público-alvo** — daltonismo, tela com brilho alto, impressão em
  preto e branco — e é o canal que some primeiro nas condições em que este produto é usado: um
  celular na rua, com pressa, depois de receber uma mensagem assustadora.
- **Tema claro fixo é escolha de honestidade, não de preguiça.** Duas paletas significam verificar
  contraste duas vezes, e a verificação é o que dá valor ao requisito — um tema escuro não
  conferido seria pior que não ter tema escuro, porque pareceria cuidado sem ser.
- **As etapas voltam na Fase 5 porque a espera passa a ser real.** Com OCR (≤5 s) e APIs externas
  (≤5 s), o ADR-0002 admite pior caso de ~15 s, e tela morta por 15 segundos faz o usuário
  recarregar a página. Traduzir as etapas para a linguagem do usuário mantém a informação e
  descarta o jargão: o que a pessoa precisa saber é que o sistema está trabalhando, não qual
  módulo está rodando.
- **A barra percentual está fora em definitivo porque seria mentira.** O pipeline não sabe quanto
  falta: as etapas paralelas terminam fora de ordem e qualquer porcentagem seria animação
  arbitrária. Numa defesa em que a pergunta é "de onde vem esse número?", a resposta honesta
  ("de lugar nenhum") custa mais do que a barra vale. Isto é reconciliação com o mockup, não
  errata: o RFC descreve uma intenção de UX que continua válida — dar sinal de vida durante a
  espera — e o que muda é como ela é cumprida.
- **Resultado na mesma página é decisão de privacidade.** Uma rota `/resultado` exigiria carregar
  a mensagem na URL ou em storage do navegador; assim ela não sai da memória da aba. Custo: não há
  link para um resultado específico — o que, para conteúdo que o usuário acabou de colar, é
  vantagem.
- A recomendação por nível é texto do frontend nesta fase. Na Fase 7 ela passa a vir da API, com o
  texto atual servindo de contingência quando a LLM não responder (RNF08).
