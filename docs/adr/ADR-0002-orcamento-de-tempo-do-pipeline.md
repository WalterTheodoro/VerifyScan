# ADR-0002 — Orçamento de tempo do pipeline

**Data:** 2026-08-27 · **Status:** aceito · **Fase:** 0

## Contexto

RNF01 e o KPI da §1.6 exigem resposta em **menos de 30 segundos**. O pipeline da §3.1 tem sete
etapas, quatro delas dependendo de I/O externo (OCR local mas caro, RDAP, VirusTotal, Safe
Browsing, LLM). Sem orçamento declarado por etapa, "menos de 30s" é aspiração: o primeiro timeout
mal escolhido em produção estoura o requisito e ninguém sabe qual etapa culpar.

Um detalhe de ordenação importa: **o OCR não pode rodar em paralelo com as heurísticas de texto**,
porque o texto que ele extrai *é a entrada* delas (§5.4.5, passo 3). O paralelismo real só começa
depois que existe texto.

## Opções consideradas

1. Timeout global único na requisição. Simples, mas não diz onde o tempo foi gasto e degrada tudo
   junto.
2. **Orçamento por etapa, com timeout explícito em cada I/O externo**, e paralelismo onde a
   dependência de dados permite.

## Decisão

Orçamento em duas fases, **série e depois paralelo**:

| Etapa | Orçamento | Execução |
|---|---|---|
| OCR (quando há imagem) | ≤ 5 s | **série**, antes de tudo |
| Heurísticas locais (texto, URL, e-mail) | ≤ 300 ms | paralelo |
| RDAP (idade do domínio) | ≤ 3 s | paralelo |
| Reputação externa (VirusTotal, Safe Browsing) | ≤ 5 s | paralelo |
| LLM (AIFormulator) | ≤ 5 s | série, no fim |

Pior caso ≈ **5 + 5 + 5 = 15 s**, com folga para rede e serialização dentro dos 30 s do RNF01.
Todo I/O externo tem timeout explícito — nenhum cliente HTTP roda com o default da biblioteca.
Estouro de orçamento degrada a etapa, nunca derruba a análise (ADR-0003).

## Consequências

- A linha de invariante do `CLAUDE.md` §5.8 que dizia "todas em paralelo" estava errada quanto ao
  OCR e foi corrigida junto com este ADR.
- Log estruturado com a duração de cada etapa passa a ser requisito da Fase 9 — sem ele o
  orçamento não é verificável e o número da monografia não é reproduzível.
- Análises com imagem são estruturalmente mais lentas que as de texto puro. As duas medições vão
  separadas no capítulo de resultados; misturá-las esconde os 5 s do OCR na média.
