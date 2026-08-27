# VerifyScan — Plano de Execução

Destino no repositório: `docs/plano-de-execucao.md`

---

## Por que não seguir o cronograma M1–M10 do RFC ao pé da letra

O RFC organiza o trabalho **por módulo** (TextAnalyzer → DomainAnalyzer → OCR → APIs → e-mail →
Scoring → IA → Frontend). Isso é ótimo como sumário de arquitetura e péssimo como ordem de
construção: seguindo essa sequência, a primeira coisa demonstrável só aparece por volta da
semana 16, e a calibração dos pesos — que é o que sustenta o KPI de precisão > 85% — cai no
finalzinho (M9), quando não há mais tempo de reagir se o número vier ruim.

O plano abaixo mantém **todo o escopo do RFC**, apenas reordenado em **fatias verticais**: cada
fase entrega algo que roda de ponta a ponta. O mapeamento para os marcos originais está na
última seção, para você mostrar continuidade ao professor.

Três inversões importantes em relação ao RFC:

1. **Corpus rotulado sai do M9 para a Fase 2.** Os pesos da tabela 5.4.7 são hipóteses até serem
   medidos. Sem corpus você não tem como calibrar nem como defender o 85% na banca.
2. **APIs externas depois da heurística própria, não antes.** O diferencial do trabalho é o
   algoritmo próprio; VirusTotal e Safe Browsing são enriquecimento. Além disso, a cota gratuita
   é apertada (ver Fase 4) e não dá para depender dela em desenvolvimento.
3. **Frontend mínimo já na Fase 1**, crescendo junto. Um backend sem tela não se demonstra.

---

## Fase 0 — Fundação

**Objetivo:** ter um esqueleto que roda do zero em máquina limpa, com testes e qualidade
automatizados. Nenhuma regra de negócio ainda.

Entregas:
- Monorepo `backend/` + `frontend/` + `docs/` + `corpus/`
- `docker-compose.yml` com Postgres 16 e Redis 7
- FastAPI com `GET /health` que checa banco e Redis
- Next.js com uma página que consome `/health`
- `uv` configurado, `ruff`, `mypy`, `pytest` com 1 teste real passando
- Alembic inicializado (sem tabelas ainda)
- `.env.example`, `.gitignore`, `README.md` de setup **para Windows**
- GitHub Actions rodando lint + testes no push
- `CLAUDE.md` na raiz, `docs/diario.md` criado

**Gate 0:** clonar o repo em uma pasta nova, seguir só o README e chegar em `/health` verde e
`pytest` passando. Se precisar de um passo não documentado, o gate falhou.

---

## Fase 1 — Fatia vertical de texto (o esqueleto do produto)

**Objetivo:** texto entra, risco sai, tela mostra. Sem OCR, sem APIs externas, sem IA, sem login.

Entregas:
- `POST /api/analises` recebendo `{ texto: string }`
- `TextAnalyzer` com as 6 categorias do RFC 5.4.1, lendo padrões de `scoring/regras.yaml`
- `URLExtractor` (URL completa, sem protocolo, encurtada, embutida em texto) + normalização
- `ScoringEngine` agregando fatores → score → BAIXO / MÉDIO / ALTO
- Schemas Pydantic do contrato de resposta (`nivel_risco`, `score`, `fatores[]`, flags de
  degradação já previstas, mesmo que sempre `false` por enquanto)
- Tela de análise + tela de resultado no Next.js, com foco em acessibilidade desde já:
  fonte grande, contraste AA, o nível de risco nunca comunicado **só** por cor (cor + ícone + texto)
- Testes unitários por categoria de padrão

**Gate 1:** colar uma mensagem real de golpe de PIX na tela e ver ALTO com os fatores listados,
em menos de 1 segundo. Demonstrável para o orientador.

---

## Fase 2 — Corpus e calibração (a fase que salva a banca)

**Objetivo:** transformar "os pesos são esses" em "os pesos são esses **porque medimos**".

Entregas:
- `corpus/casos/` com **no mínimo 150 casos rotulados**, sendo pelo menos 60 negativos
  (mensagens legítimas: cobrança real de banco, promoção real de loja, boleto de condomínio).
  Formato YAML: `id`, `conteudo`, `rotulo` (golpe / legitimo), `fonte`, `data`, `observacoes`.
- **Anonimização obrigatória** antes de commitar: substituir nomes, telefones, CPFs, valores e
  números de conta por placeholders. Documentar o procedimento em `corpus/README.md` — isso vira
  parágrafo do capítulo de LGPD.
- `tools/avaliar_corpus.py`: roda o pipeline sobre o corpus e emite precisão, recall, F1, matriz
  de confusão e a lista dos piores erros
- **Baseline de comparação** (essencial para o capítulo de resultados): um classificador trivial
  (ex.: "contém link + palavra PIX → golpe") medido no mesmo corpus. Sem baseline, o 85% não
  significa nada.
- Primeira rodada de calibração dos pesos, com o antes/depois registrado em `docs/diario.md`
- A avaliação roda no CI e falha se a precisão cair abaixo de um limiar

**Gate 2:** relatório de métricas gerado por comando, com número superior ao baseline, e você
capaz de explicar em uma frase por que cada peso ajustado mudou.

> Fonte dos casos: prints e mensagens de familiares e colegas (com consentimento), grupos
> públicos de alerta de golpe, e-mails de phishing na sua própria caixa de spam. Registre a
> proveniência caso a caso — a banca pode perguntar.

---

## Fase 3 — DomainAnalyzer

**Objetivo:** detectar fraude só pelo domínio, sem depender de terceiros.

Entregas:
- Typosquatting por distância de Levenshtein contra lista versionada de marcas
  (`scoring/marcas.yaml`) — cuidado com falso positivo em domínios curtos; use limiar
  proporcional ao tamanho, não absoluto
- Subdomínio enganoso (marca aparece no subdomínio, não no domínio registrável) — usar a
  **Public Suffix List**, não split por ponto, senão `.com.br` quebra tudo
- TLD de alto risco (lista em config)
- Idade do domínio — **usar RDAP** (`rdap.registro.br`, `rdap.org`) em vez de WHOIS texto puro:
  é JSON padronizado, tem endpoint HTTP e não exige parsing frágil. WHOIS só como fallback.
- Cada verificação com teste próprio + casos adicionados ao corpus

**Gate 3:** `bradesc0.com`, `bradesco.conta-segura.com` e `premio-agora.xyz` classificados
corretamente; `bradesco.com.br` e `catolicasc.org.br` **não** geram falso positivo.

---

## Fase 4 — Reputação externa + cache

**Objetivo:** enriquecer sem criar dependência.

> ⚠️ **Descoberta que afeta a arquitetura:** a API pública do VirusTotal permite **4 requisições
> por minuto e 500 por dia**, e os termos dizem que ela não deve ser usada em produtos
> comerciais. Isso é frontalmente incompatível com o RNF02 (100 usuários simultâneos) se cada
> análise chamar a VT direto. A resposta não é ignorar — é transformar isso em decisão de
> arquitetura documentada, o que na verdade **fortalece** o trabalho.

Entregas:
- Interface `ProvedorReputacao` com três implementações: `VirusTotalProvider`,
  `SafeBrowsingProvider`, `FakeProvider` (determinístico, usado em todos os testes)
- **Só consulta de relatório existente na VT** (`GET /urls/{id}`, onde o id é o base64url da URL
  sem padding). Se retornar 404, **não** submeter a URL e ficar esperando análise — marcar como
  "sem dados" e seguir. Submeter-e-aguardar estoura o orçamento de 30s e queima cota.
- Cache Redis por hash SHA-256 da **URL canonicalizada** (host minúsculo, sem fragmento, regra
  explícita para query string) com TTL 24h
- Rate limiter local respeitando 4 req/min, com fila e *fail fast*: se a vez não chegar em N
  segundos, degrada
- Chamadas externas em paralelo (`asyncio.gather`) com timeout individual
- Google Safe Browsing via Lookup API (confirmar a versão vigente na documentação no momento da
  implementação)
- ADR registrando o limite de cota e a estratégia de degradação

**Gate 4:** derrubar a rede (ou apontar as chaves para valores inválidos) e a análise continuar
retornando resultado coerente, em menos de 10s, com `verificacao_externa_indisponivel: true`.

---

## Fase 5 — OCR

Entregas:
- `OCRProcessor` com Tesseract, idioma `por`
- Pré-processamento: escala de cinza, aumento de contraste, binarização adaptativa, upscale de
  imagens pequenas (prints de celular costumam vir em resolução baixa)
- Processamento 100% em memória — **nunca** gravar o arquivo (RNF06), com teste que verifica isso
- Texto extraído entra no mesmo caminho da Fase 1
- Limite de tamanho e validação de tipo de arquivo (proteção contra upload malicioso)
- Fluxo alternativo: texto insuficiente → mensagem pedindo descrição manual
- Casos de OCR adicionados ao corpus (prints reais, inclusive borrados)

**Nota Windows:** o Tesseract não vem no `pip`. Instalar o binário (build do UB Mannheim), marcar
o pacote de idioma português e apontar `TESSERACT_CMD` no `.env`. Documente no README — é o passo
que mais trava colega tentando rodar seu projeto.

**Gate 5:** print real de WhatsApp classificado corretamente ponta a ponta.

---

## Fase 6 — EmailAnalyzer

Entregas:
- Parsing com `email` da stdlib (não regex artesanal)
- Divergência entre nome exibido e domínio do remetente
- Leitura de `Authentication-Results` para SPF/DKIM/DMARC quando o usuário colar o cabeçalho
  completo; ausência de cabeçalho é *ausência de sinal*, não sinal negativo — não pontuar
- Corpo → `TextAnalyzer`; links → `URLExtractor` → `URLChecker` + `DomainAnalyzer`

**Gate 6:** phishing real da sua caixa de spam classificado como ALTO; e-mail legítimo de banco
como BAIXO.

---

## Fase 7 — AIFormulator

Entregas:
- Cliente Anthropic com `claude-haiku-4-5`, `temperature` ~0.3, `max_tokens` baixo
- Assinatura tipada que **torna impossível** passar conteúdo bruto (RF13) + teste que garante isso
- Prompt de sistema com as 4 regras do RFC 5.6 (pt-BR simples; nunca inventar fator fora da lista;
  tom direto e não alarmista; terminar com recomendação de ação)
- Timeout de 5s + contingência (RNF08) + teste que simula a API fora do ar
- Teste anti-alucinação: rodar N vezes com o mesmo payload e verificar que nenhum fator externo à
  lista aparece na saída
- Contabilizar tokens por análise para estimar custo (útil no capítulo de viabilidade:
  a tabela de preços vigente do Haiku 4.5 é de US$ 1 / milhão de tokens de entrada e
  US$ 5 / milhão de saída — confirme no momento da escrita)

**Gate 7:** com a chave inválida, a análise ainda responde com score e fatores.

---

## Fase 8 — Autenticação, histórico e LGPD

Entregas:
- Modelos `Usuario`, `Analise`, `IndicadorRisco` + migrações Alembic
- Cadastro/login com bcrypt + JWT com expiração
- Histórico com filtro por nível de risco
- Regra do anônimo: 1 análise por sessão — via cookie de sessão + rate limit por IP.
  **Não** implementar fingerprinting de navegador (problema de LGPD e desnecessário).
- Exclusão de conta e de todos os dados sob demanda (RFC 7.1), com teste
- Rate limiting nas rotas, sanitização de entrada, cabeçalhos de segurança

**Gate 8:** criar conta, fazer 3 análises, ver histórico, excluir a conta e confirmar no banco
que não sobrou nada.

---

## Fase 9 — Endurecimento

Entregas:
- Teste de carga (Locust ou k6) contra o RNF02, **com os provedores externos mockados** — e a
  medição honesta do que acontece com eles ligados. Os dois números vão para a monografia.
- Revisão de acessibilidade: navegação por teclado, leitor de tela, contraste, tamanho de alvo
  de toque. Este é o público-alvo do trabalho; é conteúdo de capítulo, não polimento.
- Responsividade real em celular
- Segunda rodada de calibração com o corpus ampliado
- Observabilidade mínima: log estruturado com duração por etapa do pipeline

**Gate 9:** métricas finais fechadas — precisão, tempo médio, taxa de degradação — todas geradas
por comando reproduzível.

---

## Fase 10 — Monografia e defesa

- Capítulo de metodologia a partir de `docs/diario.md`
- Capítulo de arquitetura a partir dos ADRs (você já vai ter 10–15)
- Capítulo de resultados a partir do relatório de avaliação (com baseline e matriz de confusão)
- Limitações honestas: cota da VT, dependência do Tesseract, viés do corpus, ausência de
  validação com usuários idosos reais se não houver tempo
- Roteiro de demonstração ao vivo com plano B gravado em vídeo

---

## Mapeamento para os marcos do RFC

| Fase | Marcos do RFC cobertos |
|---|---|
| 0 | M1 |
| 1 | M2 (parte) + M8 (parte) |
| 2 | M9 (antecipado) |
| 3 | M3 |
| 4 | M5 |
| 5 | M4 |
| 6 | M6 |
| 7 | M7 |
| 8 | M2 restante + M8 restante |
| 9 | M9 |
| 10 | M10 |

Nenhum marco foi eliminado. O RFC não precisa ser reescrito — se o orientador perguntar, a
justificativa é: **entrega incremental com validação empírica antecipada**.

---

## Riscos de execução (que o RFC não cobre, porque são seus, não do sistema)

| Risco | Mitigação |
|---|---|
| O agente escreve código que você não entende e a banca pergunta | Regra fixa: você revisa cada módulo antes do commit. Se não conseguir explicar, peça para simplificar. |
| Contexto do agente estoura e ele começa a inventar | Uma fase por sessão, `/clear` entre fases, `CLAUDE.md` sempre atualizado. |
| Corpus pequeno demais → métrica sem valor estatístico | Meta de 150+ casos na Fase 2, ampliando a cada fase. |
| Escopo cresce (integração WhatsApp, app mobile) | O RFC já tem seção "Fora do Escopo". Ela é sua defesa. Releia antes de aceitar qualquer ideia nova. |
| Falta de dado real de golpe para testar | Comece a coletar **hoje**, em paralelo à Fase 0. É a tarefa com maior tempo de espera. |
