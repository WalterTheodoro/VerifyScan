# ADR-0022 — Links e domínios: análise só léxica, sem nunca abrir o link

**Data:** 2026-10-27 · **Status:** aceito · **Fase:** 3 (fatia 8) · complementa o ADR-0004 §3
(as duas heurísticas de domínio), o ADR-0009 (forma canônica) e o ADR-0020 (o que a IA recebe e o
que a limpeza tira)

## Contexto

Até a fatia 7, link não pesava nada: `https://correios-rastreio.example/taxa` sozinho saía BAIXO,
com score 0, e 46 golpes do corpus ficavam em score 0. A tela mostrava, em "Links que aparecem na
mensagem", a URL canônica inteira, pronta para copiar: exatamente o que a limpeza proíbe a IA de
escrever (ADR-0020). E a IA recebia os links normalizados num bloco próprio, como coisa a examinar.

## Princípio

**O sistema nunca faz requisição ao link da mensagem**: nem GET, nem HEAD, nem consulta DNS, nem
seguir redirecionamento, nem para "resolver" um encurtador. Três motivos:
- **Aviso ao golpista.** Muitos links de golpe são únicos por vítima (`?id=42`): o acesso diz a ele
  que a mensagem chegou e foi aberta, e o número entra na lista de "quem clica".
- **Conteúdo malicioso.** O servidor baixaria o que o golpista quiser servir.
- **SSRF.** Um link para `http://169.254.169.254/` ou para a rede interna faria o servidor do
  VerifyScan buscar o que não deve, em nome de um anônimo.

A análise é **só léxica**, sobre o texto do endereço. Reputação externa (RDAP, listas de sites
maliciosos) é a Fase 4, por API de terceiro e por consulta ao **domínio**, nunca ao link.

## Opções consideradas

- Resolver o encurtador para ver o destino × **tratar o encurtador como sinal** (o princípio acima).
- Domínio por `split(".")` × `tldextract` × lista no repositório × **`publicsuffixlist`**.
- `{dominio}` na descrição do fator × **só `{marca}`**.
- Manter `urls_analisadas` × **trocar por `links`: domínio registrável e o que se achou dele**.

## Decisão

**1. Nove sinais, um por categoria nova, todos no `regras.yaml` (seção `dominios`).**

| categoria | peso | o que dispara |
|---|---|---|
| `link_marca_nao_oficial` | 35 | nome inteiro da marca em qualquer parte do host, fora do domínio oficial |
| `link_parecido_com_oficial` | 35 | nome da marca com letra trocada no rótulo do domínio registrável |
| `link_caracteres_enganosos` | 35 | punycode (`xn--`), letra fora do ASCII ou caractere invisível |
| `link_ip` | 35 | host numérico: `1.2.3.4`, inteiro ou hexadecimal |
| `link_truque_endereco` | 25 | "@" antes do host, porta fora de 80/443, 3 ou mais subdomínios além do `www` |
| `link_encurtado` | 15 | domínio registrável numa lista de 16 encurtadores |
| `link_tld_abusado` | 15 | terminação na lista abaixo |
| `link_palavra_isca` | 15 | segurança, atualiza, regulariz, verifica, login, libera, taxa, no host ou no caminho |
| `link_sem_https` | 10 | a pessoa recebeu `http://` (o "gov.br" que o extrator completa não conta) |

- Os pesos do RFC são typosquatting +35, TLD de alto risco +15 e subdomínio enganoso +30. A marca
  fora do oficial subiu para 35 para que, sozinha, saia de BAIXO (≤ 30): é o golpe típico.
- Link para domínio oficial não dispara sinal nenhum e não baixa o nível do motor. Ele vira
  informação para a IA, e a regra do maior continua (ADR-0020).
- A agregação é a do texto (ADR-0004): cada categoria pontua uma vez, por mais links que haja.

**2. Marcas.** São 17: gov.br, Correios, Caixa, INSS, Receita Federal, Detran, Banco do Brasil, Itaú,
Bradesco, Santander, Nubank, Inter, Mercado Pago, PicPay, Serasa, WhatsApp e Instagram.
- Cada uma tem os nomes que o endereço usaria e os domínios oficiais. Um oficial cobre os
  subdomínios (`gov.br` vale para `detran.sp.gov.br`), e, num empate, ganha o mais específico.
- O nome casa como **pedaço inteiro** do host, separado por "." ou "-", ou com o rótulo inteiro sem
  hífen. Assim "inter" não casa com "internet".
- A semelhança segue o ADR-0004 §3: Levenshtein só no rótulo do domínio registrável, d ≤ 1 até 6
  letras e d ≤ 2 acima. Nome com menos de 4 letras (bb, gov) fica fora. Palavras comuns (caixa,
  inter, receita) só casam por igualdade: "intel" e "caixas" não podem virar imitação.
- Antes de comparar, o host perde acento e caractere invisível e troca 0→o e 1→l: "bradesc0" e
  "nubánk" viram imitação, e não marca exata.

**3. Public Suffix List embutida: `publicsuffixlist`.**
- Python puro, sem dependência, MPL-2.0. A lista vem dentro do pacote, e nada é baixado em
  execução: conferido no código instalado, onde só o script de atualização tem a URL da lista.
- Ela aplica a regra `*` da PSL, então terminação desconhecida é sufixo (`x.example` →
  `x.example`, igual a TLD novo).
- O `tldextract` baixa a lista e grava cache por padrão, traz quatro dependências e devolve sufixo
  vazio para terminação desconhecida. Dividir por ponto erraria todo `.com.br`.
- **Regra de dependência: não adotar versão recém-publicada.** Fixamos a mais recente publicada há
  pelo menos 14 dias quando foi adotada: `publicsuffixlist==1.1.0.20261010`. A 1.1.2.20261023 tinha
  4 dias. A versão antiga tem a mesma API (`privatesuffix`, `publicsuffix`) e dá o mesmo resultado
  nos casos do teste, `.example` incluído. A janela dá tempo de uma versão comprometida ou quebrada
  ser notada e retirada antes de chegar aqui. A regra vale para toda dependência nova daqui em
  diante.

**4. Terminações abusadas: fonte e corte.**
- Fonte dos números: Cybercrime Information Center (Interisle), *Spam Activity in TLDs, March 1 –
  May 31, 2026*, página lida em 2026-10-27, com o ranking por concentração (domínios de spam a cada
  10 mil registrados).
- Entram as **dez primeiras** por concentração: help (3.256), garden (2.336), wiki (2.323), cfd
  (1.799), qpon (1.716), xin (984), top (973), loan (967), bid (866) e rest (864).
- Ficaram de fora click (692), icu (669), bond (643), cyou (461) e sbs (418), que estão da posição
  12 à 20 na mesma página. O .xyz tem 94 por 10 mil: muito spam em número absoluto, mas diluído
  numa zona grande.
- Entram também as cinco do antigo Freenom (tk, ml, ga, cf, gq), com fonte histórica: o mesmo
  centro, em *Phishing Landscape 2023*, diz que elas responderam por 14% dos ataques de phishing no
  mundo em anos anteriores e que o Freenom parou de registrar em janeiro de 2023. Ficam porque
  domínio antigo ainda circula, não porque haja abuso novo medido.
- Contexto, sem número atribuído: o Spamhaus publica um *Domain Reputation Update* semestral (o de
  abril a setembro de 2026 saiu em 15/10). Não li as tabelas dele, e nenhum número daqui vem dele.
- Todas estão também em `urls.tlds_conhecidos`, senão `golpe.cfd` sem `http://` nem é extraído. O
  carregamento confere.

**5. A tela mostra o domínio, não o link (mudança de contrato).**
- `POST /api/analises`: **sai** `urls_analisadas` (lista de URLs canônicas) e **entra** `links`, uma
  lista de `{dominio, observacoes}`, um item por domínio registrável, na ordem em que apareceu. Ex.:
  `correios-rastreio.example` com "usa o nome Correios, mas não é um endereço oficial".
- As observações são templates do `regras.yaml` (`no_link` de cada sinal, `link_oficial` e
  `link_sem_sinal`). A do link sem sinal diz "nada estranho no endereço, mas isso não garante que o
  site é verdadeiro", nunca que ele é seguro.
- `GET /api/historico`: cada item ganha `links`, recalculado do texto guardado (o banco não guarda
  link, ADR-0009), e vazio quando o texto não existe.
- O frontend mostra o domínio como texto, nunca como `<a>`. O único cliente do contrato é o
  frontend deste repositório.

**6. A descrição do fator de link usa só `{marca}`.** O fator vai para o banco também em análise
anônima (ADR-0012), e o domínio vem da mensagem. O carregamento recusa `{dominio}` nos templates
de link.

**7. O que a IA recebe (complementa o ADR-0020).**
- O bloco `<links>` com as URLs saiu. Agora vai um bloco `<pistas>`, com o nível estimado, o que se
  achou no texto e uma linha por link ("um link: usa o nome Correios, mas não é um endereço
  oficial"), **sem endereço**. O endereço só aparece dentro da própria mensagem, como dado.
- O prompt diz que endereço oficial não prova que a mensagem é verdadeira, e que encurtador
  sozinho é comum em propaganda.
- Duas pendências da fatia 7 entram no prompt e na limpeza:
  - **Falar do sistema:** o prompt proíbe "motor", "algoritmo", "fator(es)" e "pista(s)", e a
    limpeza tira o **item** que usar uma delas. Sai só o item, nunca o nível, como na afirmação de
    segurança.
  - **"Pague a taxa pelo seu app":** mandar resolver pelo aplicativo oficial, sem link, chave Pix,
    número ou pedido de dados, é sinal de legitimidade. Sem remetente e sem outro sinal, o justo é
    no máximo MEDIO.

## Limitações declaradas

- **O corpus não exercita metade dos sinais.** Todo link do corpus é `.example`, sem IP, "@",
  porta, terminação abusada nem `http://`. Esses cinco sinais só são verificados pelos testes
  unitários (`tests/test_analisador_dominios.py`), e o efeito deles na precisão não está medido.
- **As 15 legítimas com link (0162–0176) foram escritas já sabendo os sinais**, por quem escreveu
  os sinais. Elas medem o alarme falso de um jeito favorável. Algumas foram feitas para disparar
  (encurtador de marketing, "login" no caminho de loja), mas a escolha continua sendo de quem
  conhecia a regra.
- **Domínio acentuado legítimo dispara `link_caracteres_enganosos`** (`açaí.com.br`). Separar o
  acento do homóglifo pediria a tabela de "confusáveis" do Unicode.
- **"receita" casa com qualquer `receita-de-bolo`**, e "correio" está a uma letra de "correios".
- **Homóglifos só 0→o e 1→l.** O "a" cirílico (U+0430) é pego por estar fora do ASCII, não por imitar.
- **O caso 0024 (`xn--nubnk-sqa`) decodifica para "nuàbnk"**, a duas letras de "nubank": pelo
  limiar, não é imitação, só caractere enganoso. O limiar não foi afrouxado por causa dele.
- **O histórico recalcula os links com as regras de hoje.** Os fatores, ao contrário, são os
  gravados no dia.
- **"Você colou:" ainda mostra a mensagem inteira**, com o link, na home e no histórico. É a
  mensagem que a própria pessoa colou. Escondê-la é decisão de interface e ficou como pendência.
- Sem idade do domínio nem reputação: são da Fase 4.

## Consequências

Os números são da calibração, salvo onde diz teste. O corpus tem 176 casos: 124 na calibração e 52
no teste.

- **Motor sozinho (regras v3 → v4):**

  | | calibração antes | calibração depois | teste antes | teste depois |
  |---|---|---|---|---|
  | Golpes ≥ MÉDIO | 17/67 = 25,4% | **26/67 = 38,8%** | 6/28 = 21,4% | **12/28 = 42,9%** |
  | Golpes em ALTO | 11/67 | 16/67 | 2/28 | 4/28 |
  | Alarme falso ≥ MÉDIO | 2/57 | 2/57 | 0/24 | 0/24 |
  | Alarme falso em ALTO | 0/57 | 0/57 | 0/24 | 0/24 |
  | Precisão | 89,5% | 92,9% | 100% | 100% |

  O motor ainda passa longe do KPI sozinho (recall total de 40,0%). Na calibração, nenhuma regra de
  texto tirou, sozinha, um golpe de BAIXO: quem mudou o nível foram os sinais de link, ou a soma dos
  dois. Das 13 legítimas da calibração com link, só as 2 com encurtador disparam sinal, e ficam em
  BAIXO.
- **Motor + IA, calibração** (cada linha é uma rodada):

  | rodada | precisão | recall | alarme falso ≥ MÉDIO | golpes em ALTO |
  |---|---|---|---|---|
  | antes: regras v3, prompt da fatia 7 | 89,3% | 100% | 8/57 | 65/67 |
  | regras v4, prompt da fatia 7 | 93,1% | 100% | 5/57 | 64/67 |
  | regras v4, 1ª versão do prompt novo | 91,8% | 100% | 6/57 | 63/67 |
  | regras v4, prompt final (1) | 93,1% | 100% | 5/57 | 63/67 |
  | regras v4, prompt final (2) | **94,4%** | **100%** | 4/57 | 63/67 |

  A 1ª versão do prompt novo, que já recebia a pista "link encurtado", subiu para MÉDIO as duas
  legítimas com encurtador. A frase "encurtador sozinho é comum em propaganda" as devolveu a BAIXO.
  Golpe em ALTO caiu de 65 para 63, mas todos seguem pelo menos em MÉDIO.
- **Motor + IA, teste** (rodado só no fim, duas vezes, sem ajuste depois): **P 93,3% (28/30), R
  100% (28/28)** nas duas, com os 28 golpes em ALTO e 2/24 alarmes falsos (0138 e 0148, os mesmos
  da fatia 7). As quatro legítimas novas com link ficaram em BAIXO.
- **Injeção e jargão (calibração, prompt final):**
  - Os 11 golpes de injeção seguem ALTO.
  - Em 124 respostas, "pista" apareceu uma vez e a limpeza tirou o item. "Motor", "algoritmo" e
    "fator" não apareceram.
  - "Instruções internas" e "sistema de análise", que o prompt já proibia desde a fatia 6, ainda
    chegaram à tela uma vez cada. Por isso a limpeza passou a tirar também o item com esses termos
    e com "prompt" e "injeção".
- **Amostras:** "Sua conta foi liberada! Pague agora mesmo a taxa pelo seu app" foi de ALTO para
  **MÉDIO**, e as versões com link e com chave Pix seguem ALTO. Na mesma rodada, "fatura pelo
  aplicativo oficial" foi de BAIXO para MÉDIO e "assistente de vendas" de MÉDIO para ALTO, numa
  rodada só. Fica para observar.
- **Latência:** p50 de 2,4 s com IA, máxima de 5,1 s. A análise local inteira de uma mensagem com
  três links (texto e links) levou 0,9 ms, longe dos 300 ms das heurísticas (ADR-0002).
- O gate do CI foi regravado (regras v4, corpus de 176 casos).
