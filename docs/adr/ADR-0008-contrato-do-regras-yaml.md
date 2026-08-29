# ADR-0008 — Contrato do `regras.yaml`: padrões, normalização e validação no boot

**Data:** 2026-08-29 · **Status:** aceito · **Fases:** 1, 2, 3

## Contexto

A invariante 5 do `CLAUDE.md` diz que pesos e padrões vivem em `scoring/regras.yaml`, versionado,
e que mudar um peso não pode exigir mudar código. Isso resolve *onde* o dado mora e deixa três
perguntas abertas, todas com consequência direta na Fase 2, quando o arquivo passa a ser editado
à mão a cada rodada de calibração:

1. Em que forma um padrão é escrito — termo literal ou expressão regular — e como ele encontra o
   texto do usuário, que chega com acento, maiúscula, quebra de linha e espaço duplo.
2. Quando o arquivo é validado. Um YAML com erro de edição pode falhar na subida do processo ou
   na primeira requisição do usuário.
3. Como a `descricao` do fator é escrita, dado que o ADR-0004 já decidiu que ela é template e não
   texto livre, mas não fixou o mecanismo.

## Opções consideradas

- **Casamento:** termos literais com `str.__contains__` × **expressão regular**.
- **Insensibilidade a acento e caixa:** `re.IGNORECASE` mais variantes acentuadas escritas à mão
  em cada padrão × **um normalizador aplicado aos dois lados**.
- **Validação:** na primeira leitura, sob `lru_cache` × **no `criar_app()`**.
- **Template da descrição:** só string fixa na Fase 1, placeholders quando a Fase 3 precisar ×
  **mecanismo completo desde já**.

## Decisão

**1. Padrão é regex, escrita entre aspas simples.** Termo literal não expressa "verbo seguido de
CPF em até 15 caracteres", que é o que separa golpe de aviso legítimo. Aspas simples porque em
aspas duplas o YAML processa a barra invertida e `\d`, `\b` não chegam inteiros à regex.

**2. O mesmo normalizador roda no texto e no padrão.** `normalizar()` — minúsculas, sem acento
(NFKD), espaços colapsados — é aplicado ao conteúdo do usuário e, no carregamento, a cada padrão.
Isso permite escrever `'últimas horas'` no YAML e casar com `ÚLTIMAS\n  HORAS`.

*Consequência que obriga uma regra:* como a normalização faz `.lower()`, uma classe de regex
maiúscula viraria a minúscula correspondente — `\D` → `\d`, `\S` → `\s`, `\W` → `\w`, `\B` → `\b`.
A regex continuaria compilando e passaria a significar **o oposto**. O carregamento **recusa**
qualquer padrão com classe maiúscula, com mensagem explícita.

**3. Validação no `criar_app()`, não no `lifespan` nem sob demanda.** Categorias da §5.4.1
presentes e sem repetição, pesos positivos, faixas ordenadas, TLDs minúsculos, toda regex
compilando. Um `regras.yaml` quebrado derruba o processo na subida.

**4. O mecanismo de template entra completo na Fase 1**, mesmo com todas as descrições sendo
strings fixas. `ModeloDescricao` valida no carregamento que todo `{placeholder}` pertence a um
conjunto fechado e tipado (`ValoresDescricao`: `dominio`, `marca`, `engines`, `idade_dias`), e
oferece `corresponde()`, que reconhece se uma descrição pronta poderia ter saído daquele template.

## Consequências

- **Regex é o risco de desempenho do módulo.** Um padrão com retrocesso exponencial estoura o
  orçamento de 300 ms do ADR-0002 sem que nenhum teste de comportamento perceba. Daí o teste que
  analisa um texto no tamanho máximo com margem de 3x sobre o orçamento: ele não mede desempenho,
  ele pega regex catastrófica.
- **A regra da classe maiúscula é a única pegadinha do formato**, e é o preço de normalizar os
  dois lados. Sem normalizar, o preço seria maior: cada padrão precisaria de variante com e sem
  acento, e a lista dobraria de tamanho justamente no arquivo que precisa ficar legível para
  recalibração.
- **Validar no boot torna o CI um gate do YAML**, não só do código: a suíte instancia a aplicação,
  então um erro de edição na Fase 2 quebra no CI e não em produção.
- **Sem o mecanismo de template desde já, a Fase 3 seria retrofit.** E, pior, o teste da
  invariante 1 do ADR-0004 seria vazio até lá: só se pode afirmar "toda descrição corresponde a um
  template" se existir a função que confere isso. O custo de antecipar foi uma classe pequena; o
  custo de adiar seria reescrever a garantia central do projeto sob pressão de cronograma.
- Pesos, faixas e padrões continuam **hipóteses até a Fase 2** (ADR-0005). Este ADR decide o
  formato, não os valores.
