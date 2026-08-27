# Diário de bordo — VerifyScan

Registro honesto de cada sessão de trabalho: o que foi feito, o que deu errado e o que ficou
pendente. É matéria-prima do capítulo de metodologia da monografia — inclusive, e principalmente,
os erros.

---

## 2026-08-27 — Sessão 0: análise do RFC e decisões de fundação

### O que foi feito

- Trocado `docs/RFC-VerifyScan-v1.1.pdf` pela v1.1 real (ver abaixo).
- Criado `docs/analise-rfc-v1.1.md`: resumo do sistema, 14 achados contra a v1.1 (cada um com
  âncora de seção e status), as decisões 3.1–3.11 e as partes difíceis de defender numa banca.
- Criado `docs/errata-rfc-v1.1.md`: 7 correções no texto do RFC, cada uma dizendo onde entra e o
  que muda. **Não haverá RFC v1.2** — a errata de uma página é anexada ao documento na Fase 10.
- Criados `ADR-0001` a `ADR-0006`.
- Corrigidas as invariantes 2 e 8 do `CLAUDE.md`, por consequência do ADR-0006 e do ADR-0002.
- Nenhuma linha de código. A Fase 0 começa na próxima sessão.

### O que deu errado: a análise foi feita sobre o RFC errado

A primeira rodada desta sessão analisou `docs/RFC-VerifyScan-v1.1.pdf` e concluiu, entre outras
coisas, que RF12 e RF13 não existiam, que não havia requisito de operar sem a LLM, que a numeração
de seções do `CLAUDE.md` não batia com o documento e que o modelo de dados tinha quatro entidades
com uma tabela `URLVerificada` contradizendo o cache em Redis.

Tudo isso era verdade **sobre o arquivo que estava no repositório** — e o arquivo era a **v1.0**.
Ele tinha 21 páginas, 1 284 029 bytes, md5 `bed73a7d…` e trazia "Versão 1.0" na página de
identificação, apesar do nome `RFC-VerifyScan-v1.1.pdf`. A v1.1 real tem 40 páginas, 1 963 213
bytes, md5 `e5188c44…`, e contém RF13, RNF08, o pipeline em §5.4.x, três entidades no modelo de
dados e as seções 11 a 13 (contribuições e assinaturas).

**Causa:** o comando de setup usou curinga — `Copy-Item "$HOME\Downloads\RFC-VerifyScan*.pdf"` —
que casou cinco arquivos e copiou um por cima do outro. Sobrou o último em ordem alfabética,
`RFC-VerifyScan.pdf` (v1.0, de 23/jun), renomeado para `RFC-VerifyScan-v1.1.pdf`. O nome do
arquivo mentia sobre o conteúdo.

**Como foi detectado:** ao receber a contestação dos achados, a resposta não foi aceitá-la nem
insistir, e sim reabrir o PDF e extrair o texto — momento em que a divergência entre nome e
conteúdo apareceu, junto com a localização da v1.1 real em `~/Downloads`.

Vale registrar o que **não** aconteceu, porque a hipótese chegou a ser escrita: não houve confusão
entre as capturas de feedback das seções 11 e 13 e a descrição do documento atual. O PDF que estava
versionado não tem essas seções. O erro real foi mais simples e mais evitável — não desconfiar de
um arquivo chamado v1.1 que se identifica como v1.0 logo na segunda página.

**Efeito colateral:** o relatório da primeira rodada só existia no chat e se perdeu junto com o
contexto. Por isso a análise agora mora em `docs/analise-rfc-v1.1.md`, e por isso só quatro dos
achados originais puderam ser mapeados um a um na seção 2.1 daquele arquivo.

### Lição de processo (vale a partir de agora)

> Todo documento normativo em `docs/` carrega no diário a **contagem de páginas** e a **string de
> versão** conferidas na primeira leitura. Análise que cita um documento sem esse carimbo não é
> verificável — e foi exatamente isso que custou esta sessão.

Aplicado aqui: `docs/RFC-VerifyScan-v1.1.pdf` — 40 páginas, 1 963 213 bytes, md5
`e5188c44a6aaaf131161e67e5963e0eb`, campo "Versão" = 1.1, Julho de 2026. Conferido em 2026-08-27.

### Achado mais relevante da análise

As faixas de classificação (§5.4.7) nunca foram dimensionadas contra os pesos. A soma máxima da
tabela é 340 pontos e ALTO começa em 61 — 18% do máximo. Um SMS legítimo de banco
("Banco do Brasil informa" +15, "sua conta será suspensa" +15, "clique agora" +10) soma 40 e cai em
MÉDIO sem nenhum indicador de fraude. Como MÉDIO conta como golpe na métrica principal (ADR-0005),
esse caso vira falso positivo medido já na primeira execução da Fase 2 — o corpus denuncia o
problema sozinho. É o motivo de a definição da métrica vir antes da medição, e não depois.

### Pendências abertas

| Pendência | Natureza | Quando trava |
|---|---|---|
| **Comitê de ética / consentimento** | externa — coordenação do curso | **bloqueante da Fase 2** |
| **3.9 — cronograma** | decisão do autor | Fase 0 |
| **3.10 — deploy** | decisão do autor | Fase 9 |

**Comitê de ética.** O corpus da Fase 2 vai conter mensagens de familiares, colegas e phishing da
caixa pessoal. Isso é coleta de dados de pessoas. É preciso confirmar com a coordenação do curso se
o TCC exige submissão ao CEP e qual o registro de consentimento aceito. Se a exigência existir e
for descoberta só na Fase 9, o capítulo de resultados fica comprometido — o corpus inteiro estaria
coletado fora de conformidade. Pendência com destinatário externo: o tempo de resposta não depende
de nós, então precisa ser aberta antes do primeiro caso entrar em `corpus/casos/`.

**3.9 e 3.10** não foram decididos por escolha do autor — não decidir por ele.

### Próximo passo

Fase 0 do plano de execução: monorepo, `docker compose`, `/health`, `uv`, `ruff`, `mypy`,
`pytest`, Alembic (template async, ADR-0001), CI e README de setup para Windows.
