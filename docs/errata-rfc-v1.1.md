# Errata — RFC VerifyScan v1.1

> **Status: pendente da Fase 10.** Não haverá RFC v1.2: estas correções são anexadas ao RFC como
> uma errata de uma página. Cada item diz **onde entra** e **o que muda**, para ser levado ao
> orientador sem reabrir o documento inteiro.
>
> Origem de cada item: [`analise-rfc-v1.1.md`](analise-rfc-v1.1.md), seção 2.2.
> Documento de referência: `docs/RFC-VerifyScan-v1.1.pdf` (40 páginas, md5 `e5188c44…`).

| # | Onde entra | O que muda | Achado |
|---|---|---|---|
| 1 | §2.3 (tabela RF) e §2.2 | novo **RF14** | 3 |
| 2 | §2.4 (tabela RNF) | novo **RNF09** | 4 |
| 3 | §5.4.7 (tabela de pontuação) | separar em duas linhas | 5 |
| 4 | §7.1 (tabela LGPD) e §6 (mitigação do R-06) | "anonimizado" → "pseudonimizado" | 6 |
| 5 | §10.1 (estrutura do repositório) | bloco de código atualizado | 12 |
| 6 | §5.4.3 (DomainAnalyzer) | separar typosquatting de marca embutida | 2 |
| 7 | §5.6 (tabela de provedores) | tirar nomes de modelos de terceiros | 13 |

---

### 1 — §2.3, novo RF14 (e §2.2)

Acrescentar à tabela de Requisitos Funcionais:

> **RF14** — O sistema deve permitir que o usuário cole o conteúdo de um e-mail suspeito
> (corpo e, opcionalmente, cabeçalho completo) para análise.

E incluir na lista de casos de uso da §2.2: *"Enviar conteúdo de e-mail suspeito para análise"*.

**Por quê:** a §5.4.6 especifica o `EmailAnalyzer` em detalhe, mas o e-mail é a única entrada do
produto sem requisito funcional nem caso de uso correspondente.

### 2 — §2.4, novo RNF09

Acrescentar à tabela de Requisitos Não Funcionais:

> **RNF09** — O sistema deve permanecer operacional mesmo se as APIs externas de reputação
> (VirusTotal, Google Safe Browsing) estiverem indisponíveis ou com cota esgotada, apresentando o
> resultado das heurísticas próprias e sinalizando que a verificação externa não foi possível
> (ver §3.2 e risco R-01 da §6).

**Por quê:** a operação sem a LLM virou requisito (RNF08); a operação sem as APIs de reputação —
dependência com cota e a mais provável de falhar — só existe como fluxo alternativo e mitigação de
risco. Requisito e fluxo têm peso diferente numa avaliação.

### 3 — §5.4.7, tabela de pontuação

Substituir a linha:

> Solicitação de PIX ou dados bancários — +25

por duas linhas, alinhadas com as seis categorias da §5.4.1:

> Solicitação financeira (PIX, transferência, depósito, comprovante) — +25
> Solicitação de dados pessoais (CPF, senha, dados bancários) — +25

**Por quê:** hoje as seis categorias da §5.4.1 viram cinco linhas na tabela de pontuação. Uma
mensagem que peça PIX **e** CPF pontua 50 por uma seção e 25 pela outra — MÉDIO por uma leitura,
BAIXO pela outra.

### 4 — §7.1 e §6

Na tabela da §7.1, linha "URLs analisadas", coluna Armazenamento, e na mitigação do risco R-06 na
§6, trocar **"anonimizado por hash SHA-256"** por **"pseudonimizado por hash SHA-256"**.

**Por quê:** o espaço de URLs é enumerável e o hash não tem sal — dado o hash, a URL é recuperável
por dicionário. Dado pseudonimizado continua sob a LGPD; dado anonimizado, não. A escolha do termo
muda a obrigação legal declarada.

### 5 — §10.1, estrutura do repositório

Substituir o bloco de código pela estrutura real:

```
verifyscan/
├── docs/          # RFC, ADRs, diário, errata
├── corpus/        # casos rotulados para avaliação do motor de risco
├── frontend/      # interface web (Next.js)
└── backend/
    ├── app/
    │   ├── api/          # rotas FastAPI + AuthService
    │   ├── analyzers/    # TextAnalyzer, URLExtractor, DomainAnalyzer, EmailAnalyzer
    │   ├── ocr/          # OCRProcessor (Tesseract)
    │   ├── reputation/   # URLChecker + provedores (VirusTotal, SafeBrowsing, Fake)
    │   ├── scoring/      # ScoringEngine + regras.yaml + marcas.yaml
    │   ├── formulator/   # AIFormulator (LLM)
    │   ├── models/       # Usuario, Analise, IndicadorRisco
    │   ├── schemas/      # contrato da API (Pydantic)
    │   └── core/         # config, segurança, cache, timeouts
    ├── tools/     # avaliar_corpus e demais scripts
    └── tests/
```

**Por quê:** o apêndice põe o `AIFormulator` dentro de `scoring/` e não prevê `corpus/`, `tools/`
nem `tests/` — exatamente os diretórios que sustentam a calibração e as invariantes. Um avaliador
que comparar o documento com o repositório vai encontrar a divergência.

### 6 — §5.4.3, DomainAnalyzer

Separar o primeiro item em dois, com nomes distintos:

> **Typosquatting.** Distância de Levenshtein sobre o **rótulo de segundo nível** do domínio
> (`bradesc0` × `bradesco` → distância 1 → suspeito), com limiar proporcional ao tamanho do rótulo
> e allowlist dos domínios legítimos avaliada primeiro.
>
> **Marca embutida.** O nome da marca aparece no domínio registrável, mas o domínio não é o
> legítimo (`itauonline.net` contém `itau`, e não é `itau.com.br` → suspeito).

E remover `itauonline.net` do exemplo de Levenshtein.

**Por quê:** `itauonline` × `itau` tem distância **6** no rótulo e **9** no domínio inteiro —
nenhum limiar de Levenshtein detecta esse caso sem gerar falso positivo em massa. São duas
heurísticas diferentes descritas sob um nome só. (Reforço: `bradesco.com.br` × `bradesco.com` dá
distância 3 no domínio inteiro — comparar domínios completos reprova o caso legítimo.)

### 7 — §5.6, tabela comparativa de provedores

Trocar os nomes dos modelos concorrentes pela descrição da categoria — "camada rápida / econômica
do provedor" — mantendo nomeado apenas o modelo escolhido, **Claude Haiku 4.5**.

**Por quê:** o próprio texto da §5.6 diz que o critério de arquitetura é a categoria de modelo e a
política de dados, não a versão. Nome de modelo de terceiro envelhece entre a escrita e a defesa e
vira pergunta fácil da banca sem trazer informação.
