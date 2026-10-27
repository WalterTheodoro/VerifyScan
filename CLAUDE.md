# CLAUDE.md — VerifyScan

> Arquivo de contexto permanente do projeto. O Claude Code lê isto em toda sessão.
> Mantenha curto e denso. Detalhe vai em `docs/`, não aqui.

## 1. O que é

VerifyScan é o TCC de Walter Theodoro Butenes Alves (Engenharia de Software — Católica SC).
Plataforma web que recebe uma mensagem suspeita (texto, link, print ou e-mail) e devolve
**nível de risco (BAIXO / MÉDIO / ALTO) + fatores identificados + recomendação**, em português
acessível a usuários com baixo letramento digital.

O coração do produto é um **pipeline heurístico próprio**. A IA **não decide risco sozinha**:
ela lê a mensagem, sugere um nível e escreve a explicação, e uma regra fixa deixa o nível final
no maior dos dois — ela pode subir, nunca baixar (ADR-0020).

Especificação completa: `docs/RFC-VerifyScan-v1.1.pdf`. Plano de execução: `docs/plano-de-execucao.md`.
Decisões: `docs/adr/`.

## 2. Stack (fixa — não trocar sem ADR)

| Camada | Tecnologia |
|---|---|
| Frontend | Next.js (App Router) + TypeScript + Tailwind |
| Backend | Python 3.12 + FastAPI + Pydantic v2 |
| Pacotes Python | `uv` (não usar pip/poetry direto) |
| ORM / migrações | SQLAlchemy 2.0 (async) + Alembic |
| Banco | PostgreSQL 16 |
| Cache | Redis 7 (TTL 24h) |
| OCR | Tesseract + `pytesseract` (idioma `por`) |
| LLM | Anthropic API — `claude-haiku-5-5`, SDK `anthropic`, saída estruturada (ADR-0020) |
| Testes | pytest + pytest-asyncio + httpx.AsyncClient |
| Lint/format | ruff (lint + format) + mypy no backend |
| Infra local | Docker Compose (Postgres + Redis) |

Ambiente de desenvolvimento: **Windows**. Não gerar `Makefile`. Comandos devem funcionar em
PowerShell. Nada de `&&` encadeado em scripts do `package.json` sem alternativa cross-platform.

## 3. Comandos

```powershell
# subir dependências de infra
docker compose up -d

# backend
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --port 8000 --loop none --reload   # --loop none: ver ADR-0007

# qualidade (rodar sempre antes de commitar)
uv run ruff format .
uv run ruff check . --fix
uv run mypy app
uv run pytest -q                       # integração pulada sem TEST_DATABASE_URL
uv run pytest -q -m integracao         # só os que falam com o Postgres de teste
uv run pytest -q -m "not integracao"   # só unitários, sem banco

# banco de teste (uma vez) e conferência de esquema
docker compose exec postgres createdb -U verifyscan verifyscan_teste
uv run alembic check                   # falha se modelo e migração divergirem

# avaliação do motor de risco contra o corpus rotulado
uv run python -m tools.avaliar_corpus

# análise com IA contra a API real, 13 amostras sintéticas (fora do CI; usa a chave do .env)
uv run python -m tools.testar_ia

# frontend
cd frontend
npm install
npm run dev        # http://localhost:3000
npm run lint
```

## 4. Estrutura

```
verifyscan/
├─ CLAUDE.md
├─ docker-compose.yml
├─ docs/
│  ├─ RFC-VerifyScan-v1.1.pdf
│  ├─ plano-de-execucao.md
│  ├─ diario.md            # log de sessões — vira capítulo da monografia
│  └─ adr/                 # ADR-000N-titulo.md
├─ corpus/
│  ├─ casos/               # YAML rotulado, anonimizado
│  └─ README.md            # proveniência e critério de rotulagem
├─ backend/
│  └─ app/
│     ├─ api/              # rotas FastAPI (finas, sem regra de negócio)
│     ├─ services/         # a regra de negócio mora aqui — é o destino do que api/ não pode ter
│     ├─ analyzers/        # TextAnalyzer, URLExtractor, DomainAnalyzer, EmailAnalyzer
│     ├─ ocr/              # OCRProcessor
│     ├─ reputation/       # URLChecker + provedores (VirusTotal, SafeBrowsing, Fake)
│     ├─ scoring/          # ScoringEngine, regras.yaml, respostas.yaml (plano B), combinar()
│     ├─ formulator/       # análise com IA: cliente, prompt, saída e limpeza (ADR-0020)
│     ├─ models/           # SQLAlchemy: Analise, IndicadorRisco, Usuario, SessaoUsuario
│     ├─ schemas/          # Pydantic (contrato da API)
│     └─ core/             # config, segurança (hash Argon2id), cache, logs, timeouts
│  ├─ alembic/versions/    # migrações (0001 análise, 0002 usuários e sessões, 0003 vínculo
│  │                       #   análise→conta, 0004 texto só com dono, 0005 níveis do motor e da
│  │                       #   IA + explicação só com dono); esquema só por aqui
│  ├─ tools/               # scripts (avaliar_corpus, testar_ia + amostras_ia.yaml, etc.)
│  └─ tests/
│     └─ integracao/       # únicos testes com banco: Postgres de TEST_DATABASE_URL (§6)
└─ frontend/
   ├─ next.config.ts       # proxy /api/* e /health → API_URL_INTERNA (ADR-0014)
   └─ app/
      ├─ page.tsx          # análise e resultado na mesma página (ADR-0010)
      ├─ entrar/ cadastro/ # telas de conta (página de servidor + formulario.tsx cliente)
      ├─ conta/            # "Minha conta": layout com menu + historico/ dados/ privacidade/
      │                    #   (rotas aninhadas, ADR-0016)
      ├─ privacidade/      # aviso de privacidade público (mesmo componente da conta)
      ├─ status/           # diagnóstico de infraestrutura, não é tela de usuário
      ├─ _componentes/     # cabeçalho, área de sessão, rodapé, campo de senha, avisos do envio,
      │                    #   raiz-da-pagina (elemento único na raiz; rolagem do Next 16),
      │                    #   nivel-risco (palavra + ícone), aviso-privacidade,
      │                    #   resultado (placa do resultado: home e histórico, ADR-0018; com IA,
      │                    #   tipo, sinais e passos dela, ADR-0020)
      └─ _lib/             # chamadas ao backend (conta.ts, historico.ts, gestao-conta.ts), aviso de
                           #   conta excluída (sessionStorage) e os hooks de envio e carga
```

## 5. Invariantes — nunca violar

Estas regras vêm do RFC e são o que sustenta a defesa do trabalho. Se uma tarefa parecer exigir
quebrar uma delas, **pare e pergunte**.

1. **A LLM lê a mensagem só como dado e nunca decide sozinha** (RF13 pela errata 13, ADR-0020).
   A mensagem vai entre delimitadores, escapada, e o prompt diz que ela nunca é instrução. O nível
   final é o **maior** entre o do motor e o sugerido pela IA — ela pode subir, nunca baixar —,
   garantido em `combinar()`, no `RegistroAnalise` e no CHECK `ck_analises_nivel_e_o_maior`. O que
   ela escreve só chega à tela depois de limpo (sem link, e-mail, telefone nem HTML, e sem
   afirmação positiva de segurança). As descrições dos fatores do motor seguem sendo só templates
   do `regras.yaml`, sem trecho da mensagem. Existe teste para cada parte.
2. **Nenhuma imagem é persistida além do ciclo de vida da requisição** (RNF06): nunca em banco,
   nunca em diretório da aplicação, nunca em log. O teste verifica que (a) nada foi escrito na
   árvore do projeto e (b) o arquivo temporário não sobrevive ao request — redação que mantém
   `pytesseract` viável (ADR-0006).
3. **O sistema funciona sem a LLM** (RNF08). Desligada (`IA_ATIVADA=false`), fora do ar, acima de
   15 s, recusando, cortada ou com resposta inválida: a resposta sai só do motor, com o plano B do
   nível (`scoring/respostas.yaml`) e `explicacao_indisponivel: true`. A análise nunca falha por
   causa da IA. A saída da IA e a mensagem nunca vão para log.
4. **O sistema funciona sem as APIs externas.** VirusTotal e Safe Browsing são *enriquecimento*.
   Timeout curto, falha silenciosa, flag `verificacao_externa_indisponivel: true`.
5. **Pesos e padrões vivem em `scoring/regras.yaml`**, versionado — nunca espalhados como números
   mágicos no código. Mudar peso não pode exigir mudar código. As respostas do plano B, uma por
   nível, vivem em `scoring/respostas.yaml`; o sistema nunca diz "não é golpe".
6. **Toda análise registrada grava todos os seus `IndicadorRisco` na mesma transação** (tipo,
   descrição, peso): nunca análise sem indicador nem conjunto parcial. Sem isso não há auditoria
   nem recalibração. Falha ao registrar não derruba a análise: a transação inteira é descartada,
   vira WARNING sem conteúdo da mensagem e a resposta sai igual (ADR-0012).
7. **Nada de segredo no repositório.** Chaves só via `.env` (com `.env.example` versionado).
8. **Orçamento de tempo** (KPI < 30s): OCR ≤ 5s **em série** (o texto extraído é a entrada das
   heurísticas) · depois, em paralelo: heurísticas locais ≤ 300ms · RDAP ≤ 3s · reputação externa
   ≤ 5s · por fim LLM ≤ 15 s, uma chamada, sem nova tentativa (ADR-0020) · registro ≤ 2 s, em série,
   por último (ADR-0012). Pior caso ≈ 27 s (hoje, só texto, ≈ 17 s); o proxy do Next corta em 90 s
   (ADR-0014). A folga do KPI no desenho completo é de 3 s: com OCR e reputação, o teto da IA baixa
   para análise com imagem. Todo I/O externo tem timeout explícito (ADR-0002).

## 6. Convenções de código

- Português nos nomes de domínio (`nivel_risco`, `IndicadorRisco`, `fatores`), inglês em
  termos técnicos consagrados (`cache`, `token`, `handler`). Não misturar dentro do mesmo conceito.
- Type hints obrigatórios no backend; `mypy` limpo.
- Rotas FastAPI são finas: validam entrada, chamam um *service*, devolvem schema. Zero regra de
  negócio em `api/`.
- Analisadores são funções/classes puras: entram dados, saem `list[Fator]`. Sem I/O direto, sem
  acesso a banco. Isso é o que os torna testáveis e é o que será medido contra o corpus.
- **Extrator não é analisador.** Quem só encontra e normaliza — `URLExtractor`, `OCRProcessor` —
  devolve o próprio tipo (`list[URLExtraida]`, texto), não `list[Fator]`: extrair não pontua, e
  o peso do que foi extraído pertence a quem analisa depois. Mesma pureza, saída diferente.
- Todo acesso a rede fica atrás de uma interface com uma implementação *fake* determinística
  usada nos testes. Teste não faz chamada de rede — nunca. **Única exceção:** testes marcados
  `integracao` (em `tests/integracao/`) falam com um Postgres de teste — o do docker compose ou o
  serviço do CI, via `TEST_DATABASE_URL` —, **nunca com o Neon**. Esquema só pelo Alembic, nenhuma
  linha deixada para trás. Motivo: o bug do ADR-0007 só apareceu contra Postgres real.
- Commits em português, imperativo, escopo curto: `feat(scoring): agrega pesos por categoria`.
  Um commit por unidade lógica. Nada de commit gigante de fim de sessão.
- Mensagens ao usuário final em pt-BR, tom direto e não alarmista, sem jargão técnico.

## 7. Como trabalhar comigo (regras para o agente)

- **Planeje antes de escrever.** Em qualquer tarefa que toque mais de 2 arquivos, apresente o
  plano e espere aprovação.
- **Uma tarefa por vez.** Não adiantar fases do plano. Não "aproveitar para arrumar" coisas fora
  do escopo pedido — anote em `docs/diario.md` e siga.
- **Em rodada de correção, corrija UM item por vez**, na ordem em que foi listado. Confirme antes
  de passar ao próximo.
- **Teste antes do código** sempre que houver comportamento verificável. Escreva o teste que
  falha, depois implemente.
- **Não instale dependência nova sem perguntar.** Justifique por que a biblioteca padrão ou o que
  já existe não resolve.
- **Não gere código que eu não consiga explicar numa banca.** Prefira o óbvio ao esperto. Se uma
  solução exigir um truque, comente o porquê em uma linha.
- Ao terminar uma tarefa: rode `ruff`, `mypy`, `pytest`, mostre o resultado e o diff resumido.
- Se algo no RFC estiver ambíguo ou errado, diga — não invente e não finja que está resolvido.

## 8. Definition of Done (por tarefa)

- [ ] Testes novos passam e a suíte inteira continua verde
- [ ] `ruff check` e `mypy` limpos
- [ ] Nenhuma invariante da Seção 5 violada
- [ ] Se mudou comportamento do motor de risco: `avaliar_corpus` rodado, métricas anotadas em
      `docs/diario.md` (antes → depois)
- [ ] Se foi uma decisão de arquitetura: ADR criado em `docs/adr/`
- [ ] Uma linha em `docs/diario.md` com o que foi feito e o que ficou pendente
- [ ] Commit feito

## 9. Contexto acadêmico

Isto é um TCC. A banca vai perguntar **por quê**, não só **o quê**. Portanto:

- Toda escolha não óbvia vira um ADR de 15 linhas (contexto, opções, decisão, consequência).
- O `docs/diario.md` é matéria-prima do capítulo de metodologia — mantenha-o honesto, incluindo
  o que deu errado.
- Números de precisão só valem se vierem do script de avaliação sobre o corpus. Nunca afirme
  precisão sem medição.

