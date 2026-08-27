# VerifyScan — Prompts para o Claude Code

Destino no repositório: `docs/prompts-claude-code.md`

Todos os prompts abaixo são para colar **direto** no Claude Code, sem edição, salvo onde estiver
marcado `⟨...⟩`. As decisões de projeto já estão embutidas — você não precisa lembrar de nada.

---

## Regras de operação (leia uma vez)

1. **Modo Plano.** `Shift+Tab` até aparecer *plan mode*. Use em toda tarefa nova. O agente
   planeja, você lê, você aprova. Só então ele escreve.
2. **Uma fase por sessão.** Ao terminar uma fase, `/clear`. Contexto longo é a causa número um
   de código incoerente.
3. **`CLAUDE.md` é a memória.** Se você corrigir a mesma coisa duas vezes, a correção vira linha
   no `CLAUDE.md`, não uma terceira correção.
4. **Commit antes de qualquer tarefa grande.** É o seu botão de desfazer.
5. **Nunca aceite um diff que você não leu.** Você é quem vai defender isso.

---

## Prompt 0 — Abertura do projeto (primeira sessão, repositório vazio)

> Pré-requisito: crie a pasta do projeto, `git init`, e coloque dentro `CLAUDE.md`,
> `docs/plano-de-execucao.md`, `docs/prompts-claude-code.md` e o PDF do RFC em `docs/`.

```
Leia CLAUDE.md, docs/plano-de-execucao.md e docs/RFC-VerifyScan-v1.1.pdf por inteiro antes de
responder qualquer coisa.

Não escreva código nesta sessão. Nenhum arquivo além dos que eu pedir explicitamente abaixo.

Sua tarefa é de análise. Entregue, em português, nesta ordem:

1. Um resumo em até 15 linhas do que o sistema faz e de onde está a complexidade real.
2. Toda contradição, ambiguidade ou lacuna que você encontrar entre o RFC, o CLAUDE.md e o plano
   de execução. Seja específico: cite seção e o que exatamente não fecha. Não suavize.
3. As decisões técnicas que precisam estar travadas antes da Fase 0 e que hoje não estão em
   lugar nenhum. Para cada uma, proponha uma opção e diga o custo de estar errado.
4. Uma lista das partes deste projeto que, na sua avaliação, um estudante de graduação teria
   dificuldade de explicar em uma banca se fossem geradas por IA — e como simplificá-las sem
   perder o requisito.

Depois disso, crie APENAS estes arquivos:
- docs/adr/ADR-0001-stack-e-ferramentas.md
- docs/adr/ADR-0002-orcamento-de-tempo-do-pipeline.md
- docs/adr/ADR-0003-degradacao-sem-apis-externas.md
- docs/diario.md (com a entrada de hoje)

Formato do ADR: Contexto / Opções consideradas / Decisão / Consequências. Máximo 20 linhas cada.
```

---

## Prompt 1 — Fase 0: Fundação

```
Fase 0 do docs/plano-de-execucao.md. Entre em modo plano antes de escrever qualquer coisa.

Objetivo: esqueleto do monorepo rodando do zero, sem nenhuma regra de negócio.

Decisões já tomadas — não me pergunte sobre elas, apenas siga:
- Python 3.12, gerenciado com uv. Backend em backend/, frontend em frontend/.
- FastAPI + Pydantic v2. SQLAlchemy 2.0 async + Alembic (inicializado, sem tabelas ainda).
- Next.js App Router + TypeScript + Tailwind.
- Postgres 16 e Redis 7 via docker compose.
- ruff (lint + format) e mypy no backend. pytest + pytest-asyncio.
- Meu ambiente é Windows. Não crie Makefile. Todo comando do README precisa funcionar em
  PowerShell. Scripts do package.json devem ser cross-platform.

Entregas:
1. Estrutura de pastas conforme a Seção 4 do CLAUDE.md, com os pacotes vazios criados.
2. docker-compose.yml com Postgres e Redis, healthchecks e volumes nomeados.
3. GET /health no backend que verifica conexão real com Postgres e com Redis e retorna o status
   de cada um separadamente.
4. Uma página no Next.js que chama /health e mostra o resultado. Sem estilo elaborado.
5. .env.example com todas as variáveis que o projeto vai precisar até a Fase 8, comentadas.
   Nenhum valor real. .gitignore cobrindo .env, __pycache__, .venv, node_modules, .next.
6. Um teste real em backend/tests/ (não um placeholder) que suba a app com httpx.AsyncClient e
   verifique /health, com Postgres e Redis mockados.
7. GitHub Actions rodando ruff, mypy e pytest no push.
8. README.md com o passo a passo de setup no Windows, incluindo a instalação do Tesseract com o
   pacote de idioma português (mesmo que ainda não seja usado nesta fase).

Definition of Done: ruff, mypy e pytest verdes; docker compose up -d seguido dos comandos do
README chega em /health com os dois serviços OK.

Ao terminar: mostre o resumo do diff, o resultado dos comandos, atualize docs/diario.md e faça o
commit.
```

---

## Prompt 2 — Fase 1: Fatia vertical de texto

```
Fase 1 do docs/plano-de-execucao.md. Modo plano primeiro.

Objetivo: texto entra pela tela, nível de risco sai. Sem OCR, sem API externa, sem IA, sem login.

Decisões já tomadas:
- Padrões e pesos ficam em backend/app/scoring/regras.yaml, carregados e validados com Pydantic
  na inicialização. Nenhum peso ou regex hardcoded em .py. Popule o YAML com as 6 categorias e os
  pesos da Seção 5.4.1 do RFC.
- Analisadores são puros: recebem string, devolvem list[Fator]. Sem I/O, sem banco, sem rede.
- Fator = { tipo, descricao, peso, categoria }. IndicadorRisco (persistência) vem só na Fase 8;
  por ora o Fator existe apenas em memória.
- O schema de resposta já deve prever os campos de degradação: explicacao_indisponivel e
  verificacao_externa_indisponivel, ambos false nesta fase. Não quero mudar contrato depois.
- Faixas: 0–30 BAIXO, 31–60 MÉDIO, 61+ ALTO. Vem do RFC 5.4.7.

Entregas:
1. POST /api/analises recebendo { texto: string } e devolvendo score, nivel_risco, fatores[] e
   as duas flags.
2. TextAnalyzer com as 6 categorias: urgência, personificação de marca, ameaça/bloqueio, prêmio
   falso, solicitação financeira, pedido de dados pessoais.
3. URLExtractor: URL completa, sem protocolo, encurtada, e embutida em texto corrido. Normalize
   para uma forma canônica (host minúsculo, sem fragmento) e devolva também a forma original.
4. ScoringEngine agregando os fatores.
5. Frontend: tela de entrada e tela de resultado.

Restrições de interface — o público-alvo inclui idosos e pessoas com baixo letramento digital,
isso não é enfeite, é requisito do RFC:
- O nível de risco nunca pode ser comunicado só por cor. Sempre cor + ícone + palavra.
- Contraste mínimo AA. Fonte base 18px ou maior. Alvos de toque de no mínimo 44px.
- Nenhum jargão técnico visível ao usuário. "Fatores identificados", não "heurísticas detectadas".

Testes: um caso por categoria de padrão, mais casos negativos que NÃO devem pontuar. Inclua um
teste com uma mensagem legítima de banco que não pode ser classificada como golpe.

Definition of Done: colo uma mensagem de golpe de PIX na tela e vejo ALTO com os fatores em menos
de 1 segundo. Suíte verde, ruff e mypy limpos.
```

---

## Prompt 3 — Fase 2: Corpus e avaliação

```
Fase 2 do docs/plano-de-execucao.md. Modo plano primeiro. Esta é a fase mais importante do
trabalho para a defesa — trate com cuidado.

Objetivo: infraestrutura de avaliação empírica do motor de risco. Eu forneço os casos reais;
você constrói o mecanismo.

Entregas:
1. Formato do corpus: um arquivo YAML por caso em corpus/casos/, com os campos id, conteudo,
   rotulo (golpe | legitimo), canal (whatsapp | sms | email | site | outro), fonte, data,
   observacoes. Escreva o schema Pydantic que valida todos eles e um teste que falha se algum
   arquivo estiver malformado.
2. corpus/README.md documentando o critério de rotulagem e o procedimento de anonimização
   (nomes, telefones, CPF, valores, números de conta, e-mails → placeholders padronizados).
   Escreva também tools/anonimizar.py que faz uma primeira passada automática e me aponta o que
   precisa de revisão manual. Ele nunca deve sobrescrever o original sem confirmação.
3. tools/avaliar_corpus.py: roda o pipeline sobre todo o corpus e imprime precisão, recall, F1,
   acurácia, matriz de confusão e a lista dos 10 piores erros com os fatores que dispararam.
   Saída legível no terminal e também em JSON para eu versionar.
4. Um baseline trivial para comparação, em tools/baseline.py: "contém URL E contém palavra
   relacionada a pagamento → golpe". Medido pelo mesmo script, lado a lado com o motor real.
5. 20 casos de exemplo que você mesmo escreve, claramente marcados como sintéticos no campo
   fonte, só para o mecanismo ter o que rodar. Eles NÃO entram na métrica final — o script deve
   permitir filtrar por fonte.
6. Um teste no CI que roda a avaliação e falha se a precisão cair abaixo de um limiar definido
   em config.

Não invente casos "reais". Se um caso for sintético, o campo fonte diz sintetico. A honestidade
do corpus é o que dá validade ao capítulo de resultados.

Ao terminar, escreva docs/adr/ADR-000⟨N⟩-metodologia-de-avaliacao.md explicando por que
precisão e recall importam de forma diferente aqui (um falso negativo significa alguém caindo em
um golpe; um falso positivo significa alguém desconfiando de uma mensagem legítima) e qual dos
dois o projeto prioriza.
```

---

## Template genérico — usar nas Fases 3 a 9

```
Fase ⟨N⟩ do docs/plano-de-execucao.md: ⟨nome da fase⟩. Modo plano primeiro.

Leia a seção correspondente do plano e a seção do RFC que a especifica antes de planejar.

Decisões já tomadas:
- ⟨cole aqui as decisões da fase, tiradas do plano⟩

Escopo desta sessão: apenas o que está listado na fase. Se você identificar algo importante fora
do escopo, anote em docs/diario.md em uma seção "Pendências" e siga em frente — não implemente.

Restrições permanentes (releia a Seção 5 do CLAUDE.md): nenhuma invariante pode ser quebrada.
Se a tarefa parecer exigir isso, pare e me pergunte.

Testes: escreva primeiro os que falham, depois implemente. Nenhum teste pode fazer chamada de
rede real.

Se esta fase mexer no motor de risco, rode tools/avaliar_corpus.py antes e depois e registre as
duas medições em docs/diario.md.

Definition of Done: ⟨cole o Gate da fase⟩. Além disso: ruff, mypy e pytest verdes; diário
atualizado; commit feito.
```

---

## Prompt de correção pontual

Use quando um review (seu, do orientador ou de colega) apontar vários problemas. **Não cole a
lista inteira de uma vez.**

```
Vou passar correções uma de cada vez. Corrija SOMENTE o item que eu der, mostre o diff, rode os
testes e pare. Não antecipe os próximos itens, não refatore o que está em volta, não "aproveite
para melhorar" nada.

Item 1: ⟨descrição do problema⟩
Arquivo(s) provável(is): ⟨se souber⟩
Comportamento esperado: ⟨o que deveria acontecer⟩
```

Depois: `Confirmado, funcionou. Item 2: ...`

---

## Prompt de gate (fim de fase)

```
Fase ⟨N⟩ concluída. Faça a verificação de gate antes de eu fechar a sessão.

1. Releia o Gate da Fase ⟨N⟩ em docs/plano-de-execucao.md e verifique item por item, com
   evidência: comando executado e saída. Não afirme que passou sem ter rodado.
2. Revise o código desta fase contra as invariantes da Seção 5 do CLAUDE.md, uma por uma.
3. Aponte o que ficou frágil, mal testado ou merecendo refatoração. Seja crítico com o próprio
   trabalho — prefiro saber agora.
4. Liste as pendências que devem entrar em fases seguintes.
5. Me faça 3 perguntas sobre este código que uma banca de TCC faria e que eu provavelmente não
   saberia responder. Não responda por mim — só as perguntas.
6. Atualize docs/diario.md e o CLAUDE.md se alguma convenção nova se firmou nesta fase.
```

O item 5 é o mais valioso do prompt. Use.

---

## Prompt de ADR avulso

```
Preciso registrar uma decisão de arquitetura: ⟨assunto⟩.

Escreva docs/adr/ADR-000⟨N⟩-⟨slug⟩.md no formato Contexto / Opções consideradas / Decisão /
Consequências, máximo 20 linhas. As opções precisam ser opções de verdade, com o argumento de
quem defenderia cada uma — não uma escolhida e duas de palha. Diga explicitamente o que estamos
perdendo com a decisão.
```

---

## Prompt de fechamento de sessão

```
Fechando a sessão. Sem escrever código novo:

1. Resuma o que foi feito hoje em até 10 linhas.
2. Atualize docs/diario.md com a entrada de hoje: feito, medições (se houve), decisões,
   pendências, o que deu errado.
3. Se alguma convenção, comando ou armadilha nova apareceu hoje, adicione ao CLAUDE.md — no
   lugar certo, sem inchar o arquivo.
4. Diga qual é o próximo passo concreto e qual prompt do docs/prompts-claude-code.md eu devo usar.
5. Verifique se há algo não commitado.
```

---

## Prompt para a monografia (Fase 10)

```
Não escreva código. Preciso de material para a monografia.

Leia docs/diario.md, docs/adr/ e a saída mais recente de tools/avaliar_corpus.py.

Produza um rascunho do capítulo ⟨metodologia | arquitetura | resultados⟩ em português acadêmico
formal, ABNT, terceira pessoa.

Regras:
- Nenhum número que não esteja no relatório de avaliação ou no diário. Se faltar dado, escreva
  [MEDIR: ...] no lugar em vez de estimar.
- Nenhuma afirmação de eficácia sem a medição correspondente.
- Inclua as limitações reais, incluindo as que pegam mal: cota da API pública do VirusTotal,
  tamanho e viés do corpus, ausência de validação com usuários finais reais se for o caso.
- Marque com [CITAR: ...] todo ponto que precisa de referência bibliográfica.

Escreva em docs/monografia/⟨capitulo⟩.md.
```

---

## Anti-padrões — o que não colar no Claude Code

| Prompt ruim | Por que | O que fazer |
|---|---|---|
| "Implementa o VerifyScan seguindo o RFC" | Escopo de 20 semanas em uma mensagem; sai um esqueleto plausível e oco | Uma fase por vez |
| "Arruma esses 8 problemas" | Ele conserta mal os oito | Um por vez, confirmando |
| "Melhora o código" | Sem critério, vira refatoração aleatória | "Reduza a duplicação entre X e Y sem mudar comportamento; os testes devem continuar passando" |
| "Cria os testes" (depois do código) | Testes escritos para passar no código existente não testam nada | Teste que falha primeiro |
| "Tá dando erro" | Ele adivinha | Cole o traceback inteiro, o comando e o que você esperava |
| "Pode usar a biblioteca que achar melhor" | Dependência que você não sabe justificar na banca | Você decide; ele argumenta se discordar |
