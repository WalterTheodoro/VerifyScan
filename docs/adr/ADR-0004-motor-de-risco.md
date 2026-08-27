# ADR-0004 — Motor de risco: agregação, fatores e domínios

**Data:** 2026-08-27 · **Status:** aceito · **Fases:** 1, 3

## Contexto

O RFC descreve *quais* padrões pontuam (§5.4.1, §5.4.3, §5.4.7) mas não *como* eles se somam,
*o que* pode aparecer na descrição de um fator, nem *sobre que string* a distância de Levenshtein
é calculada. Três lacunas que decidem o comportamento do produto e duas contradições registradas
em `analise-rfc-v1.1.md` (achados 2 e 5).

## Opções consideradas

- Agregação: somar **por ocorrência** (cada casamento pontua) × somar **por categoria** (cada
  categoria pontua uma vez).
- `Fator.descricao`: texto livre gerado no código × **template versionado com placeholders
  tipados**.
- Domínios: uma heurística "typosquatting" genérica sobre o domínio inteiro × **duas heurísticas
  nomeadas** com unidades de comparação diferentes.

## Decisão

**1. Agregação por categoria.** Cada categoria pontua no máximo uma vez, com o peso da categoria,
independentemente de quantos padrões dela casarem. O score é soma livre, sem teto. O `regras.yaml`
declara `agregacao: por_categoria` explicitamente — a regra é dado, não comportamento implícito do
código.

**2. `Fator.descricao` é template.** Template versionado no `regras.yaml`, com placeholders
preenchidos apenas por valores de um conjunto fechado e tipado: domínio normalizado, contagem de
engines, idade em dias, nome da marca imitada. **Nunca** um trecho do texto do usuário. O teste da
invariante 1 verifica que toda `descricao` produzida corresponde a um dos templates.

**3. Domínios: duas heurísticas separadas, nomeadas e com pesos distintos.**
- **Typosquatting** — Levenshtein sobre o **rótulo de segundo nível apenas**, limiar proporcional
  (d ≤ 1 para rótulos de até 6 caracteres, d ≤ 2 acima), com a allowlist dos domínios legítimos
  avaliada **primeiro**.
- **Marca embutida** — token da marca presente no domínio registrável, sem que o domínio esteja na
  allowlist.

O `marcas.yaml` guarda as duas unidades: domínios registráveis legítimos (`bradesco.com.br`) e
tokens de marca (`bradesco`).

**4. Seis categorias de texto, não cinco.** O motor implementa as seis da §5.4.1 — "solicitação
financeira" e "dados pessoais" são categorias distintas, de +25 cada. A §5.4.7 do documento é que
está errada, e a errata corrige.

## Consequências

- **Agregação:** somar por ocorrência introduziria viés de comprimento — textos longos ficariam
  automaticamente mais perigosos, e "colar a mesma frase dez vezes" seria a pergunta fatal na
  banca. Trocar isso depois invalidaria toda calibração anterior e obrigaria a reavaliar o corpus.
- **Descrição:** a invariante 1 é o diferencial conceitual do projeto. Um único fator embutindo
  texto do usuário torna falsa a afirmação "a IA não vê o conteúdo" e derruba o argumento de
  privacidade inteiro.
- **Domínios:** com Levenshtein sobre o domínio completo, `bradesco.com.br` × `bradesco.com` dá
  distância 3 e o Gate 3 reprova o caso legítimo que existe para proteger; e `itauonline.net` ×
  `itau.com.br` dá 9 — nenhum limiar razoável o alcança. Separar as heurísticas é o que faz os
  dois casos funcionarem ao mesmo tempo.
- Pesos e limiares aqui são **hipóteses até a Fase 2**; a calibração e as métricas ficam no
  ADR-0005.
