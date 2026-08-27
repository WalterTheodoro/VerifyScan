# Análise do RFC — VerifyScan v1.1

> **Proveniência.** Gerado a partir de `docs/RFC-VerifyScan-v1.1.pdf` — **40 páginas**,
> **1 963 213 bytes**, md5 `e5188c44a6aaaf131161e67e5963e0eb`, campo "Versão" = **1.1**
> (Julho de 2026). Leitura em **2026-08-27**, com o texto extraído por `pdftotext -layout`.
> Toda âncora de seção citada aqui foi conferida nesse arquivo — nenhuma foi citada de memória.
>
> Este documento substitui o relatório da primeira sessão, que foi produzido sobre um PDF
> desatualizado (conteúdo da v1.0 sob o nome `RFC-VerifyScan-v1.1.pdf`) e nunca foi gravado em
> disco. O episódio está registrado em [`diario.md`](diario.md).

**Legenda de status**

| Status | Significado |
|---|---|
| **RESOLVIDO (ADR-000N)** | decidido nesta sessão; o ADR citado carrega a justificativa |
| **ERRATA** | exige mudança no texto do RFC — ver [`errata-rfc-v1.1.md`](errata-rfc-v1.1.md), pendente da Fase 10 |
| **ABERTO** | ainda precisa de decisão; consta como pendência no diário |
| **DESCARTADO** | avaliado e deixado de lado, com o motivo em uma linha |

---

## 1. Resumo — o que o sistema faz e onde está a complexidade real

O VerifyScan recebe uma mensagem suspeita (texto, link, print ou e-mail) e devolve nível de risco,
fatores identificados e recomendação, em português acessível. O fluxo é o da §3.1: o OCR extrai
texto de imagens, o `URLExtractor` acha os links, `TextAnalyzer`, `DomainAnalyzer`, `URLChecker` e
`EmailAnalyzer` produzem fatores, o `ScoringEngine` (§5.4.7) soma pesos e classifica, e o
`AIFormulator` (§5.4.8) transforma o resultado estruturado em texto — sem nunca ver o conteúdo
bruto (RF13).

A complexidade real **não** está na LLM nem nas integrações. Está em três pontos:

1. **Calibração.** Pesos e faixas da §5.4.7 são hipóteses escritas sem dado. O KPI de precisão
   (§1.6) só significa alguma coisa contra um corpus rotulado, com métrica definida antes da
   medição (achados 1 e 10).
2. **Domínios.** Typosquatting e marca embutida são problemas diferentes que o RFC trata como um
   só (achado 2); é onde mora o falso positivo constrangedor — o domínio real de um banco.
3. **Degradação.** Três dependências externas com cota, latência e disponibilidade fora do nosso
   controle (VirusTotal, Safe Browsing, LLM). O sistema precisa dar resposta útil sem nenhuma
   delas (RNF08 e achado 4).

O resto — FastAPI, Tesseract, Redis, Postgres — é montagem conhecida.

---

## 2. Contradições, ambiguidades e lacunas

### 2.1 O que sobrou dos achados da primeira rodada

A lista original não foi persistida: só os quatro itens citados na contestação podem ser mapeados
um a um. Os demais não existem mais como texto e foram refeitos do zero na §2.2.

| Item original | Veredito contra a v1.1 |
|---|---|
| 2.1 "RF12 e RF13 não existem" | **CAIU** — existem (p. 9). RF12 é o histórico; RF13 é a invariante 1 |
| 2.2 "não há requisito de operar sem a LLM" | **CAIU** — RNF08 (p. 9), §3.2 (4º fluxo alternativo) e risco R-04 (§6) |
| 2.3 "a numeração de seções do CLAUDE.md não bate com o RFC" | **CAIU** — §5.4.1, §5.4.7, §5.5 e §5.6 conferem |
| 2.16 "quatro entidades, com `URLVerificada`, contradizendo o cache" | **CAIU** — §5.5 diz três entidades e a nota de arquitetura da §5.4.4 explica por que o cache vive só no Redis |

Os quatro caíram pelo mesmo motivo: descreviam a v1.0.

### 2.2 Achados contra a v1.1

**1. As faixas de classificação nunca foram dimensionadas.** §5.4.7 (tabela de pontuação e faixas)
× §5.4.1 (pesos de texto).

A soma máxima da tabela §5.4.7, uma ocorrência de cada fator, é **340 pontos**
(10+15+15+15+20+20+20+25+25+30+30+35+40+40). ALTO começa em 61 — **18% do máximo**.
Simulação com um SMS legítimo de banco: "Banco do Brasil informa" (personificação de marca, +15)
+ "sua conta será suspensa" (ameaça de bloqueio, +15) + "clique agora" (urgência, +10) = **40 →
MÉDIO**. Uma cobrança bancária real cai em MÉDIO sem nenhum indicador de fraude. As faixas foram
escritas junto com os pesos, sem dado.

*Ressalva de leitura:* "URL flagrada no VirusTotal (1–2 engines)" (+20) e "(3+ engines)" (+40) são
mutuamente exclusivos para a mesma URL, então 340 é o teto literal da tabela e **320** o teto
atingível por uma URL; 61 continua entre 18% e 19% do máximo. O achado não muda.

→ **RESOLVIDO (ADR-0005)**

**2. O exemplo de typosquatting está errado.** §5.4.3.

A seção afirma que a distância de Levenshtein identifica tanto `bradesc0.com` quanto
`itauonline.net`. Para `bradesc0` × `bradesco` a afirmação procede (rótulo de 2º nível, distância
**1**). Para `itauonline` × `itau` a distância é **6** no rótulo e **9** no domínio inteiro
(`itauonline.net` × `itau.com.br`) — Levenshtein não detecta, com nenhum limiar que não gere falso
positivo em massa. O RFC funde duas heurísticas distintas sob um nome só; `itauonline.net` só é
alcançável por **marca embutida**.

Reforço do mesmo problema: `bradesco.com.br` × `bradesco.com` dá distância **3** no domínio
inteiro — comparar domínios completos reprova exatamente o caso legítimo que a heurística deveria
proteger.

→ **ERRATA** (documento) + **RESOLVIDO (ADR-0004**, que separa e nomeia as duas heurísticas**)**

**3. Não existe RF para e-mail.** §5.4.6 (EmailAnalyzer) × §2.2 (casos de uso) × §2.3 (RF01–RF13).

O módulo de e-mail está especificado em detalhe, mas colar um e-mail não é caso de uso nem
requisito funcional. É a única entrada do produto sem RF.

→ **ERRATA** (novo RF14)

**4. Não existe RNF para operar sem VirusTotal / Safe Browsing.** §2.4 × §3.2 × §6 (risco R-01).

A operação sem a LLM virou requisito (RNF08). A operação sem as APIs de reputação — que é a
dependência com cota e a mais provável de falhar — aparece só como fluxo alternativo e como
mitigação de risco. Requisito e fluxo têm peso diferente numa banca.

→ **ERRATA** (novo RNF09) + **RESOLVIDO (ADR-0003)** no código

**5. §5.4.1 e §5.4.7 discordam sobre as categorias de texto.** As seis categorias da §5.4.1 viram
cinco linhas na tabela de pontuação: "Solicitação financeira" (+25) e "Dados pessoais" (+25)
fundem-se em "Solicitação de PIX ou dados bancários" (+25). Uma mensagem que peça PIX **e** CPF
pontua 50 pela §5.4.1 e 25 pela §5.4.7 — 50 é MÉDIO, 25 é BAIXO.

→ **ERRATA** (documento) + **RESOLVIDO (ADR-0004)** (comportamento do motor)

**6. "Anonimizado por hash SHA-256" é impreciso.** §7.1 (tabela LGPD, linha "URLs analisadas") e
§6 (mitigação do risco R-06).

O espaço de URLs é enumerável e o hash não tem sal: dado o hash, a URL é recuperável por
dicionário. Isso é **pseudonimização**, não anonimização — a diferença é justamente o que decide
se o dado continua sob a LGPD.

→ **ERRATA**

**7. WHOIS × RDAP.** §5.4.3 (idade do domínio) × Fase 3 do `plano-de-execucao.md`.

O RFC fixa consulta WHOIS; o plano troca por RDAP (JSON padronizado, endpoint HTTP, sem parsing
frágil). Divergência entre documentos que precisa de decisão registrada, não de errata.

→ **RESOLVIDO (ADR-0001)**

**8. RNF02 × cota do VirusTotal.** §2.4 (100 usuários simultâneos) × §5.4.4 (VirusTotal no caminho
da análise).

A API pública do VirusTotal é limitada e vedada a uso comercial; nenhuma arquitetura entrega 100
simultâneos passando por ela. O requisito não está errado — está subespecificado quanto a qual
caminho ele mede.

→ **RESOLVIDO (ADR-0003)**

**9. `Analise.texto_input` permanente contradiz o escopo declarado.** §5.5 (modelo de dados) ×
§2.6 ("não armazenará conteúdo de terceiros citado nas mensagens analisadas") × RNF06 × §7.1
("Texto enviado — permanente, somente usuários autenticados").

O texto do usuário é guardado indefinidamente, e ele contém, por definição, conteúdo de terceiros:
nome de remetente, telefone, valor, número de conta. Falta regra explícita do que se guarda —
íntegra, trecho ou nada.

→ **RESOLVIDO (ADR-0006)**

**10. O KPI de precisão não define métrica.** §1.6 ("Precisão na identificação de golpes > 85% em
testes com casos reais").

Precisão, acurácia, recall e F1 dão números diferentes sobre o mesmo corpus, e nada diz de que
lado MÉDIO conta. Sem isso, "85%" é escolha *a posteriori*.

→ **RESOLVIDO (ADR-0005)**

**11. O ORM está citado sem paradigma nem driver.** §5.6, tabela "Comunicação entre módulos":
"API Backend → PostgreSQL — SQL, via ORM (SQLAlchemy)". Síncrono e assíncrono levam a códigos
incompatíveis, e o erro só aparece sob carga.

→ **RESOLVIDO (ADR-0001)**

**12. A estrutura do repositório do apêndice diverge da real.** §10.1 × `CLAUDE.md` §4.

O apêndice põe o `AIFormulator` dentro de `scoring/` e não prevê `corpus/`, `tools/` nem `tests/`
— justamente os diretórios que sustentam a calibração e as invariantes. Um avaliador que comparar
documento e repositório vai notar.

→ **ERRATA**

**13. A tabela comparativa de provedores nomeia modelos de terceiros.** §5.6 ("OpenAI — linha
mini/nano (GPT-5.4)", "Google — linha Flash (Gemini)").

O próprio texto da §5.6 diz que o critério é categoria de modelo e política de dados, não versão.
Nome de modelo concorrente envelhece entre a escrita e a defesa e vira pergunta fácil da banca sem
trazer informação.

→ **ERRATA**

**14. RF06 e RF08 descrevem a mesma capacidade.** §2.3: RF06 "verificar URLs contra bases de dados
de phishing e malware" e RF08 "verificar a reputação de domínios via APIs externas (VirusTotal,
Google Safe Browsing)". A redundância não muda nada no código nem na rastreabilidade.

→ **DESCARTADO** — redundância sem efeito prático

---

## 3. Decisões travadas antes da Fase 0

Redação aprovada pelo autor. Cada item indica onde foi registrado.

**3.1 — Regra de agregação do score.** → ADR-0004

Cada categoria pontua no máximo uma vez, com o peso da categoria, independentemente de quantos
padrões dela casarem; score é soma livre, sem teto; `regras.yaml` ganha um campo
`agregacao: por_categoria` explícito.

*Custo de errar:* soma por ocorrência introduz viés de comprimento — o motor passa a classificar
textos longos como mais perigosos. É o defeito mais fácil de demonstrar numa banca ("e se eu colar
a mesma frase dez vezes?") e invalida toda a calibração feita antes da correção, obrigando a
reavaliar o corpus inteiro.

**3.2 — Como MÉDIO entra no cálculo da métrica binária.** → ADR-0005

MÉDIO conta como "golpe" na métrica principal, porque um falso negativo significa alguém perdendo
dinheiro e um falso positivo significa alguém desconfiando de uma mensagem legítima — os custos
são assimétricos. Publicar também a variante com MÉDIO como "legítimo", nas duas primeiras
medições, e nunca mais mudar depois disso.

*Custo de errar:* decidir depois de ver os números é escolher o corte que dá o resultado bonito.
Se a banca perguntar "por que MÉDIO conta como golpe?" e a resposta for "porque assim dava 87%",
o capítulo de resultados morre.

**3.3 — Correções no texto do RFC.** → [`errata-rfc-v1.1.md`](errata-rfc-v1.1.md), Fase 10.
Sem RFC v1.2: uma errata de uma página.

**3.4 — O que pode entrar em `Fator.descricao`.** → ADR-0004

`descricao` é um template versionado no `regras.yaml` com placeholders preenchidos apenas por
valores de um conjunto fechado e tipado (domínio normalizado, contagem de engines, idade em dias,
nome da marca imitada). Nunca um trecho do texto do usuário. O teste da invariante 1 verifica que
a `descricao` produzida bate com um dos templates.

*Custo de errar:* a invariante 1 é o diferencial conceitual do projeto ("a IA não vê o conteúdo").
Se um único fator embutir texto do usuário na descrição, a afirmação é falsa e todo o argumento de
privacidade cai.

**3.5 — Persistência de texto: anônimo e OCR.** → ADR-0006

Análise anônima persiste apenas score, nível, fatores e timestamp — nunca `texto_input`. Texto
extraído por OCR nunca é persistido, para nenhum tipo de usuário, autenticado ou não; o histórico
do print mostra "análise de imagem" e os fatores. `Analise.texto_input` vira nullable com regra
explícita.

*Custo de errar:* migração retroativa em cima de dados já gravados, mais um furo de LGPD que já
está no documento (§2.6 × §7.1) e que a banca de Engenharia de Software provavelmente vai olhar.

**3.6 — Redação da invariante 2 (imagens) compatível com `pytesseract`.** → ADR-0006

Reescrever para "nenhuma imagem é persistida além do ciclo de vida da requisição; nunca em banco,
nunca em diretório da aplicação, nunca em log". O teste verifica que (a) nada foi escrito na
árvore do projeto e (b) o arquivo temporário não sobrevive ao request. Manter `pytesseract`.

*Custo de errar:* a Fase 5 chega a um teste impossível de passar e a saída vira ou trocar de
biblioteca no meio do projeto (`tesserocr` é sofrível de instalar no Windows) ou apagar o teste —
que é a invariante virar decoração.

**3.7 — `marcas.yaml`: unidade de comparação e limiar.** → ADR-0004

A lista contém domínios registráveis legítimos (`bradesco.com.br`) e um token de marca
(`bradesco`). Duas heurísticas separadas e nomeadas: (a) **typosquatting** = Levenshtein sobre o
rótulo de segundo nível apenas, limiar proporcional (d ≤ 1 para rótulos ≤ 6 caracteres, d ≤ 2
acima), com allowlist explícita dos domínios legítimos avaliada primeiro; (b) **marca embutida** =
token da marca presente no domínio registrável mas o domínio não estar na allowlist. Elas têm
pesos diferentes.

*Custo de errar:* com Levenshtein sobre o domínio inteiro, `bradesco.com.br` × `bradesco.com` dá
distância 3 e o Gate 3 falha exatamente no caso que ele existe para proteger. Falso positivo em
domínio de banco real é o erro mais constrangedor possível numa demo ao vivo.

**3.8 — Avaliação do corpus roda offline, sempre.** → ADR-0005

`avaliar_corpus` usa obrigatoriamente provedores fake determinísticos; RDAP e reputação vêm de
fixtures declaradas no próprio arquivo YAML do caso (`rdap_idade_dias: 3`, `vt_engines: 5`). O
relatório carimba a versão do `regras.yaml` e o hash do corpus.

*Custo de errar:* métrica que varia com a rede não é métrica. E o CI passa a quebrar por cota do
VirusTotal, o que faz o time desativar o gate de precisão — perdendo o mecanismo que a Fase 2
existe para criar.

**3.9 — Cronograma.** **ABERTO** — pendência registrada no diário; decisão do autor.

**3.10 — Deploy.** **ABERTO** — pendência registrada no diário; decisão do autor.

**3.11 — Visibilidade do repositório e gate de anonimização.** → ADR-0006

Repositório privado até a Fase 10, tornado público só depois de uma auditoria do histórico; e um
teste que roda no CI reprovando qualquer arquivo em `corpus/casos/` que contenha padrão de CPF,
telefone, e-mail ou valor monetário fora do formato de placeholder.

*Custo de errar:* é a única decisão desta lista que é irreversível. Um commit com dado real de
familiar em repositório público não se desfaz.

---

## 4. O que seria difícil defender numa banca — e como simplificar

A tabela original desta seção também se perdeu com o relatório; só se sabe que o **item 1 era
"trocar o ORM assíncrono por síncrono"**, e ele foi **recusado** — o async fica, defensável pelas
quatro regras do ADR-0001. A lista abaixo foi refeita contra a v1.1.

| Parte | Por que é difícil de defender | Como simplificar sem perder o requisito |
|---|---|---|
| SQLAlchemy async | `MissingGreenlet`, sessões expiradas e lazy loading são erros que ninguém explica sob pressão | Recusado simplificar o paradigma. As quatro regras do ADR-0001 eliminam a classe de erro; a defesa é "um paradigma só, porque o pipeline é paralelo" |
| Pesos e faixas do score | Números sem origem; a pergunta "por que 61?" não tem resposta hoje | ADR-0005: faixas e pesos viram parâmetros calibrados na Fase 2, com baseline e corpus versionado |
| Levenshtein | Fácil de citar, difícil de justificar limiar e unidade de comparação | ADR-0004: limiar proporcional, rótulo de 2º nível, allowlist primeiro — três frases explicam |
| Prompt da LLM | "A IA não decide risco" é uma afirmação forte que precisa de prova | RF13 + assinatura tipada + teste anti-alucinação (Fase 7). A prova é o teste, não o prompt |
| Paralelismo do pipeline | `asyncio.gather` com timeouts individuais é onde o código fica esperto | ADR-0002: orçamento explícito por etapa, uma linha por dependência |
| OCR | Pré-processamento de imagem vira caixa-preta | Manter o mínimo (cinza, contraste, binarização, upscale) e medir o efeito de cada passo em casos do corpus |
