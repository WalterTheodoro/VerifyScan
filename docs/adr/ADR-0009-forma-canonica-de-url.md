# ADR-0009 — Extração e forma canônica de URL

**Data:** 2026-08-29 · **Status:** aceito · **Fases:** 1, 3, 4

## Contexto

A §5.4.2 do RFC lista as quatro formas que o `URLExtractor` precisa achar — completa, sem
protocolo, encurtada e embutida em texto corrido — e diz que "cada URL é normalizada", sem dizer
o que isso significa. A definição não é detalhe de implementação: a forma canônica é a string que
o `DomainAnalyzer` analisa (Fase 3) e, hasheada em SHA-256, a chave do cache de reputação
(Fase 4). Duas grafias da mesma URL produzindo chaves diferentes desperdiçam cota da VirusTotal,
que é o recurso mais escasso do projeto.

Há também uma pergunta anterior: **o que é uma URL** num texto escrito por gente. "acesse aqui:
site.com" é link; "R$ 3,50", "Python 3.12", "arquivo.pdf" e "Obrigado.Att" não são, e todos casam
com um `\w+\.\w+` ingênuo.

## Opções consideradas

- **Host sem protocolo:** aceitar qualquer `palavra.palavra` × exigir **TLD de uma lista
  versionada**.
- **Query string:** descartar × **preservar**.
- **`usuario@host`:** preservar como digitado × **descartar o usuário**.
- **Saída do extrator:** `list[Fator]`, como os analisadores × **tipo próprio, `list[URLExtraida]`**.

## Decisão

**1. Forma canônica.** Esquema minúsculo, `http` quando ausente; host minúsculo e sem ponto final;
**usuário antes do arroba descartado**; porta padrão do esquema removida; caminho preservado como
está; **query preservada**; **fragmento removido**; caminho vazio vira `/`. A forma original que o
usuário digitou é sempre mantida ao lado.

**2. Host sem protocolo exige TLD de lista versionada** (`regras.yaml`, seção `urls`). Com
`http://` explícito não há ambiguidade e a lista não se aplica.

**3. O extrator devolve `list[URLExtraida]`, não `list[Fator]`.** Extrair não pontua: todo peso de
URL — typosquatting +35, TLD de alto risco +15, idade +20, subdomínio enganoso +30, reputação
externa +20/+40 — pertence ao `DomainAnalyzer` e ao `URLChecker`, das Fases 3 e 4.

**4. Teto de URLs por análise** (20, configurável no YAML).

## Consequências

- **Descartar o `usuario@` é a decisão de segurança deste ADR, não uma limpeza.** Em
  `http://bradesco.com.br@golpe.xyz/pix` o host real é `golpe.xyz` — é phishing clássico, e é
  exatamente a mensagem que o produto existe para pegar. Preservar a forma digitada faria a Fase 3
  medir distância de Levenshtein contra o domínio errado e devolver "parece legítimo".
- **Preservar a query e remover o fragmento não é simetria acidental.** O fragmento nunca é
  enviado ao servidor e não distingue duas páginas; a query frequentemente é a identidade da
  página do golpe (`?id=42`). Descartá-la juntaria URLs distintas na mesma chave de cache e faria
  a Fase 4 responder sobre a URL errada.
- **A lista de TLDs é dívida assumida.** Ela é finita e vai errar: um golpe em TLD fora da lista,
  escrito sem protocolo, passa despercebido. A alternativa — a Public Suffix List inteira — é uma
  dependência nova e um arquivo grande para um ganho que o corpus ainda não mostrou existir. A
  Fase 3 já traz a PSL por outro motivo (domínio registrável, `.com.br`), e nessa hora esta
  decisão deve ser revisitada com dado do corpus, não com palpite.
- **O teto de 20 URLs limita o pior caso das Fases 3 e 4**, onde cada URL custa uma consulta RDAP
  e uma de reputação. Sem ele, uma mensagem com 200 links estoura o orçamento de 30 s do RNF01
  sozinha.
- Guardar `original` junto da canônica é o que permite, mais adiante, mostrar ao usuário o link
  como ele o recebeu, sem que a análise dependa da grafia.
