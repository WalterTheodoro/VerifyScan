# ADR-0025 — Cobertura de testes: Vitest no frontend, pytest-cov no backend

**Data:** 2026-11-15 (frontend) e 2026-11-22 (backend) · **Status:** aceito · **Fase:** fatia 11

## Contexto

A prova de autoria da disciplina pede, por relatório, 75% de cobertura no backend e 25% no
frontend. O frontend tinha 7 arquivos de teste em `node:test` (86 testes), rodados direto pelo Node
com type stripping. Esse executor não carrega JSX, não lê o `tsconfig` e não resolve import sem
extensão: `historico.ts` (que importa `./conta`) e qualquer componente ficavam fora de alcance, e o
relatório de cobertura dele só lista o que foi importado. Não servia como prova do frontend
inteiro.

## Opções consideradas

- **Manter o `node:test` e medir com c8:** continua sem JSX e sem import sem extensão; os
  componentes seguiriam sem teste possível.
- **Dois executores** (`node:test` para os antigos, outro para os novos): os arquivos com
  `node:test` não rodam dentro do outro, então o que já era testado apareceria com 0% num relatório
  e o resto no outro; o `npm test` teria de encadear dois comandos (o CLAUDE.md evita `&&`).
- **Vitest para tudo**, com cobertura v8, migrando os 7 testes.

## Decisão

- **Vitest 4.1.12 + `@vitest/coverage-v8` 4.1.12**, configurado em `frontend/vitest.config.ts`.
  `npm test` é `vitest run --coverage`; o CI roda o mesmo comando.
- **Todo o `app/` no relatório, testado ou não.** O `coverage.all` do pedido não existe mais: o
  Vitest 4 o removeu e passou a reportar só o que foi importado
  (https://v4.vitest.dev/guide/migration, "Removed options `coverage.all` and
  `coverage.extensions`"). A forma vigente é o `coverage.include`: todo arquivo que casa com o
  padrão entra no relatório (https://v4.vitest.dev/config/coverage). Padrão:
  `app/**/*.{ts,tsx}`, e não `app/**`, que tentaria cobrir CSS, SVG e o `.ico`. Fora: os
  `*.test.{ts,tsx}` e os `.d.ts`. A `page.tsx` fica no denominador: tirá-la seria inflar o número.
- **Threshold de 25% de linhas** (`coverage.thresholds.lines`). Abaixo disso o comando sai com
  erro e o CI reprova. Conferido: com o threshold em 99%, o comando sai com código 1.
- **Migração dos 7 testes trocando só o import do executor** (`node:test` → `vitest`). As
  asserções continuam em `node:assert/strict`, iguais byte a byte. A única reescrita foi o relógio
  falso do `servidor.test.ts`: `mock.timers` virou `vi.useFakeTimers` com a lista explícita
  `setTimeout`, `clearTimeout` e `Date`, para o `setImmediate` do teste continuar real. Os 86
  testes passaram no Vitest antes de qualquer teste novo.
- **Componentes e hooks: jsdom 30.1.3 + Testing Library** (`@testing-library/react` 16.3.3 e o
  peer `@testing-library/dom` 10.4.2). O jsdom é a implementação de referência da Testing
  Library, mais fiel que o happy-dom em papéis ARIA, eventos e `sessionStorage`; aqui são poucos
  testes, e a fidelidade vale mais que a velocidade. O ambiente padrão continua `node`; só quem
  precisa de DOM pede o jsdom na primeira linha (`// @vitest-environment jsdom`). Sem `user-event`
  nem `jest-dom`: `fireEvent` e `node:assert` bastam. Sem plugin de React: o Vite transforma o TSX
  com o runtime automático do `tsconfig`.
- **Versões (regra do ADR-0022, ≥ 14 dias):** todas fixadas sem `^`. A linha 5 do Vitest (5.0.5,
  de 15/10) declara peer `@types/node ^22 || >=24`, e o projeto usa `^20`; adotá-la obrigaria a
  mexer numa dependência existente. A 4.1.12 (15/10) aceita `^20`. Para subir para a 5, o custo é
  `@types/node` em `^22`, que bate com o Node 22 do CI.
- **Vite 7.3.7, e não 8, com `overrides`.** O Vite é peer obrigatório do Vitest. O npm 10.9 quebra
  (`Cannot read properties of null (reading 'edgesOut')`) ao percorrer os peers opcionais do
  `@vitest/mocker`: msw → vite 8 → `@vitejs/devtools` → vitest 5. Com o Vite 8 o erro é o mesmo,
  porque o rolldown pede `@emnapi/*` 2.0 beta contra o 1.x do Tailwind. O
  `--legacy-peer-deps` instalava, mas o lock gerado não passava no `npm ci` comum (o `fdir`
  perdia o `picomatch` 4). O que resolveu: `"overrides": { "vite": "$vite" }`, que amarra todo
  pedido de Vite à versão da raiz. O lock passa no `npm ci` do npm 10, e nenhum pacote que já
  existia mudou de versão, exceto o `@types/estree` transitivo (1.0.9 → 1.0.10, de 29/10).

## Consequências

- Medido em 15/11: só a migração já dava **35,05% de linhas** (279/796). O v8, com o remapeamento
  por AST, conta linha com instrução: comentário e JSX de várias linhas valem pouco. A `page.tsx`
  tem 1092 linhas no arquivo e 141 linhas contáveis. A estimativa de ~16% contava arquivos.
- Com os testes novos de `_lib` e dos componentes simples: **158 testes, 52,01% de linhas**
  (414/796), 51,74% de instruções, 45,74% de ramos e 40% de funções.
- O relatório sai em `frontend/coverage/` (texto no terminal, HTML em `coverage/index.html` e
  `coverage-summary.json`), ignorado pelo git e pelo ESLint.
- O nome acessível calculado pela Testing Library junta "Mostrar" + `sr-only` " senha" em
  "Mostrarsenha" (apara o espaço do começo do span). O teste do campo de senha confere o texto do
  botão. Como cada leitor de tela calcula esse nome não foi verificado.
- Ficam sem teste as telas grandes de estado e rede (`page.tsx`, `resultado.tsx`, `lista.tsx`,
  `dados.tsx`, formulários, `cabecalho`, `area-sessao`, `status`) e as páginas e layouts finos.
  São conferidas pela medição de tela em 390 px; teste unitário delas seria caro e frágil.
- Os comentários de `servidor.ts`, `imagem.ts`, `cota.ts`, `ip.ts`, `falha-da-analise.ts` e
  `tela-da-analise.ts` ainda justificam "sem imports, para o teste rodar no Node direto". A regra
  deixou de ser necessária, mas não faz mal; a revisão desses comentários fica para quando esses
  arquivos mudarem.

## Backend — 2026-11-22

**Contexto:** a suíte do backend já cobria bem o código, mas não havia ferramenta declarada nem
comando documentado: o relatório não era reproduzível na prova de autoria.

**Opções consideradas:**

- **`coverage run -m pytest` + `coverage report`:** dois comandos para um relatório.
- **`pytest-cov` ligado no `addopts`:** um comando só, mas toda execução do dia a dia pagaria a
  medição.
- **`pytest-cov` pedido na linha de comando**, com a meta no `pyproject.toml`.

**Decisão:**

- **`pytest-cov` 7.1.0** no grupo `dev` (publicado em 21/03/2026; o `coverage` 7.17.0 que ele
  traz, em 22/10/2026 — os dois dentro da regra dos 14 dias do ADR-0022).
- **Comando:** `uv run pytest -q --cov=app --cov-report=term-missing`. Fica **fora do `addopts`**:
  medido, a suíte de unitários vai de 105 s para 135 s com a cobertura (+28%).
- **Meta de 75% em `fail_under`**, em `[tool.coverage.report]`, e não em `--cov-fail-under` na
  linha de comando: assim a máquina e o CI leem o mesmo número de um lugar só. Conferido: com
  `--cov-fail-under=99` o comando sai com código de erro.
- **No CI, ligada.** O passo `pytest` do job do backend ganhou o `--cov`; é a mesma execução, não
  uma segunda. O custo é da ordem de meio minuto por push, e sem o gate a meta poderia regredir
  sem ninguém ver. Lá o Postgres de teste existe, então os testes de integração contam.

**Consequências:**

- Medido em 22/11, só unitários (`-m "not integracao"`, 866 testes): **92,41%** (2622
  instruções, 199 sem cobertura). O `coverage.py` conta instruções, sem ramos (`branch` desligado,
  o padrão).
- O que os unitários não alcançam são os repositórios, que falam com o banco
  (`repositorio_uso` 49%, `repositorio_sessoes` 52%, `repositorio_usuarios` 56%,
  `repositorio_historico` 58%) e o `services/health.py` (53%). São cobertos pelos testes de
  integração; a medida com eles não foi feita nesta data, porque o Docker estava desligado. O
  número do CI é o primeiro com a integração.
- **Armadilha na máquina:** com `TEST_DATABASE_URL` no `.env` e o Postgres fora do ar, os testes
  de integração não são pulados; cada um espera a conexão falhar, e a execução demora e termina em
  erro. Na prova de autoria: subir o `docker compose` antes, ou medir com `-m "not integracao"`.
  Está no README.
