# ADR-0006 — Privacidade, persistência e o corpus

**Data:** 2026-08-27 · **Status:** aceito · **Fases:** 2, 5, 8

## Contexto

Três frentes de privacidade precisam de regra antes de existir código que grave qualquer coisa:

1. O RFC guarda `Analise.texto_input` permanentemente para usuários autenticados (§5.5, §7.1), ao
   mesmo tempo em que declara não armazenar conteúdo de terceiros citado nas mensagens (§2.6).
   Toda mensagem suspeita contém dado de terceiro: remetente, telefone, valor, número de conta
   (achado 9).
2. A invariante 2 do `CLAUDE.md` ("imagens não são persistidas") estava redigida de um jeito que
   nenhum teste passaria com `pytesseract`, que grava arquivo temporário para chamar o binário do
   Tesseract.
3. O corpus da Fase 2 vai conter mensagens reais de familiares, colegas e phishing de caixa
   pessoal — dado de pessoas, em um repositório git, cujo histórico não se apaga.

## Opções consideradas

- Persistir o texto original para todos × só para autenticados × **nunca para anônimos e nunca
  para OCR**.
- Trocar `pytesseract` por `tesserocr` (processa em memória, sem temporário) × **reescrever a
  invariante** para o que realmente importa. `tesserocr` é sofrível de instalar no Windows, que é
  o ambiente de desenvolvimento.
- Repositório público desde o início × **privado até a Fase 10**.

## Decisão

**1. Persistência de texto.** Análise anônima persiste apenas score, nível, fatores e timestamp —
nunca `texto_input`. Texto extraído por OCR **nunca** é persistido, para nenhum tipo de usuário; o
histórico de um print mostra "análise de imagem" e os fatores. `Analise.texto_input` é nullable,
com a regra escrita no modelo.

**2. Invariante 2, nova redação.** *"Nenhuma imagem é persistida além do ciclo de vida da
requisição; nunca em banco, nunca em diretório da aplicação, nunca em log."* O teste verifica que
(a) nada foi escrito na árvore do projeto e (b) o arquivo temporário não sobrevive ao request.
`pytesseract` fica.

**3. Corpus e repositório.** Repositório **privado até a Fase 10**, aberto só depois de uma
auditoria do histórico. Um teste roda no CI e reprova qualquer arquivo em `corpus/casos/` que
contenha padrão de CPF, telefone, e-mail ou valor monetário fora do formato de placeholder.

## Consequências

- Decidir isso depois custaria migração retroativa em cima de dado já gravado, mais um furo de
  LGPD que já está no documento (§2.6 × §7.1) e que uma banca de Engenharia de Software
  provavelmente vai olhar.
- A invariante 2 na redação antiga levaria a Fase 5 a um teste impossível de passar, e a saída
  seria trocar de biblioteca no meio do projeto ou apagar o teste — que é a invariante virar
  decoração.
- O item 3 é a **única decisão irreversível** desta rodada: um commit com dado real de um familiar
  em repositório público não se desfaz. Por isso o gate é automático, no CI, e não uma lembrança.
- Consequência aberta e registrada no diário: se a coordenação do curso exigir submissão ao comitê
  de ética para a coleta do corpus, isso é **bloqueante da Fase 2** — precisa ser confirmado antes
  do primeiro caso entrar em `corpus/casos/`.
