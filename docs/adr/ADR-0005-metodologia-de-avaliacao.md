# ADR-0005 — Metodologia de avaliação do motor de risco

**Data:** 2026-08-27 · **Status:** aceito · **Fases:** 2, 9

## Contexto

O KPI da §1.6 pede "precisão > 85% em testes com casos reais" sem dizer qual métrica, sobre qual
corpus, nem de que lado o nível **MÉDIO** conta (achado 10). E as faixas da §5.4.7 nunca foram
dimensionadas (achado 1): a soma máxima da tabela é **340 pontos**, ALTO começa em 61 — 18% do
máximo — e um SMS legítimo de banco ("Banco do Brasil informa" +15, "sua conta será suspensa" +15,
"clique agora" +10) soma **40** e cai em **MÉDIO** sem nenhum indicador de fraude. Pesos e faixas
foram escritos juntos, sem dado.

## Opções consideradas

- Definir o corte de MÉDIO **antes** ou **depois** de ver as métricas.
- Avaliar com provedores externos reais × com **fakes determinísticos e fixtures**.
- Calibrar só os pesos × calibrar **pesos e faixas**.

## Decisão

**1. MÉDIO conta como "golpe" na métrica principal.** Os custos são assimétricos: um falso
negativo é alguém perdendo dinheiro; um falso positivo é alguém desconfiando de uma mensagem
legítima. A variante com MÉDIO como "legítimo" é publicada junto, **nas duas primeiras medições**,
e depois disso a definição **não muda mais**.

**2. As faixas 0–30 / 31–60 / 61+ são objeto de calibração na Fase 2, tanto quanto os pesos.** O
relatório do `avaliar_corpus` carimba os **cortes vigentes**, a versão do `regras.yaml` e o hash do
corpus — toda métrica é rastreável até a configuração que a produziu.

**3. `avaliar_corpus` roda offline, sempre.** Provedores fake determinísticos obrigatórios; RDAP e
reputação vêm de fixtures declaradas no próprio YAML do caso (`rdap_idade_dias: 3`,
`vt_engines: 5`). Nenhuma chamada de rede na avaliação.

**4. Baseline obrigatório.** Um classificador trivial medido no mesmo corpus, sem o qual o número
do KPI não significa nada.

## Consequências

- **A interação entre (1) e (2) não é coincidência — é o motivo de a decisão vir antes da
  medição.** Com MÉDIO contando como golpe, aquele SMS legítimo de banco vira um **falso positivo
  medido**: o corpus denuncia sozinho o problema das faixas, na primeira execução da Fase 2. Se
  MÉDIO contasse como legítimo, o mesmo caso passaria despercebido e as faixas continuariam
  intactas até alguém reclamar em produção.
- Decidir o corte depois de ver os números seria escolher o resultado bonito. Se a banca perguntar
  "por que MÉDIO conta como golpe?" e a resposta for "porque assim dava 87%", o capítulo de
  resultados morre. Por isso a definição é congelada após as duas primeiras medições.
- Métrica que varia com a rede não é métrica; e um CI que quebra por cota da VirusTotal leva
  qualquer um a desativar o gate de precisão — perdendo justamente o mecanismo que a Fase 2 existe
  para criar.
- Mexer nas faixas invalida comparações com medições anteriores. Daí o carimbo dos cortes em todo
  relatório: o antes/depois no `diario.md` só faz sentido com as duas configurações registradas.
