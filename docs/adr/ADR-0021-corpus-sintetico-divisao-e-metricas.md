# ADR-0021 — Corpus sintético, divisão fixa e métricas da avaliação

**Data:** 2026-10-27 · **Status:** aceito · **Fase:** 2 (fatia 7) · complementa o ADR-0005 (métrica
do KPI, modo com IA) e o ADR-0006 §3 (valor monetário no corpus sintético)

## Contexto

O corpus estava vazio e a Fase 2 parada na pendência do comitê de ética, que vale para mensagens
**reais** de pessoas. Desde a fatia 6 a IA lê a mensagem e pode subir o nível, e toda mudança no
motor ou no prompt passa a precisar de número de antes e depois. Havia material sintético, sem dado
de ninguém: as baterias 1 e 2 de testes no navegador e as 20 amostras do `tools/testar_ia`. O §1.6
do RFC pede "precisão > 85% em testes com casos reais" sem dizer qual métrica (achado 10); o
ADR-0005 decidiu de que lado o MÉDIO conta, não a métrica.

## Opções consideradas

- Esperar o comitê × **corpus sintético agora**, com o real como segunda medição quando houver.
- Divisão sorteada a cada rodada × validação cruzada × **divisão fixa, sorteada uma vez**.
- KPI por precisão sozinha × acurácia × **precisão e recall**.
- Gate do CI em pontos percentuais × **em casos**.

## Decisão

**1. Corpus sintético, binário.** 161 casos em `corpus/casos/` (95 golpes, 66 legítimas): bateria 1
(71), bateria 2 (6), amostras (16) e 68 novos. Cada um tem `fonte: sintetico`, `autor`
(`claude` | `walter`), `padrao` (o **tipo** de alerta público em que se baseia, como Febraban,
Correios ou gov.br, sem copiar texto) e a origem em `observacoes`. O rótulo é `golpe` ou
`legitimo`. Caso ambíguo fica fora, e a lista dos excluídos, com o motivo, está no diário.

**2. Anonimização.** Os placeholders são `[NOME]`, `[TELEFONE]`, `[EMAIL]`, `[CPF]`, `[CHAVE_PIX]`,
`[CONTA]`, `[AGENCIA]`, `[RASTREIO]` e `[PLACA]`, e os links usam o domínio reservado `.example`.
O `tests/test_corpus.py` passa o `tools/pii.py` em todo caso. **CPF, telefone e e-mail barram
sempre.** **Valor em reais é aceito só com `fonte: sintetico`**: ali ele é fictício por construção
e é sinal (a "taxa de R$ 12,90"). Isto complementa o ADR-0006 §3, que continua valendo para caso
real.

**3. Divisão fixa.** O `tools/sortear_divisao.py` sorteia com a semente 20261027 e manda 30% de
cada rótulo para o teste. Ficaram 113 casos na calibração e 48 no teste. Ele só escreve `divisao:`
em caso que ainda não tem, e nunca muda uma existente. Os pares com `SequenceMatcher ≥ 0,85` depois
de normalizar ganham o mesmo `grupo` e caem do mesmo lado. **Regra:** o ajuste de peso, padrão ou
prompt olha só a calibração, e o teste só serve para relatar.

**4. Métricas.**
- A matriz BAIXO/MÉDIO/ALTO × golpe/legítimo.
- Golpes ≥ MÉDIO e = ALTO; alarme falso (legítimas ≥ MÉDIO e = ALTO).
- Precisão, recall, F1 e acurácia com MÉDIO = golpe, que é a principal (ADR-0005), e a variante com
  MÉDIO = legítimo.
- Tudo por divisão, no total e **por autor**, cada proporção com o IC 95% de Wilson (biblioteca
  padrão, z = 1,959964) e ao lado da linha de base trivial do ADR-0005 ("link e PIX → golpe").
- **KPI (errata 14):** atende só com precisão > 85% **e** recall > 85%. Precisão sozinha se
  consegue alarmando quase nada, e recall sozinho alarmando tudo.

**5. Dois modos.**
- `--motor` é o padrão: offline e determinístico, como manda o ADR-0005 §3, e é ele que alimenta o
  gate.
- `--com-ia` chama a API real, em série, e exige `--divisao`. Ele relata a latência contra os 30 s
  (§1.6 e RNF02), os tokens, o custo, o plano B por motivo e quantas vezes a IA subiu o nível.
- É uma **exceção declarada** ao "offline, sempre" do ADR-0005 §3: o produto final depende do
  modelo, e medir só o motor não mede o produto. Fica fora do CI, o carimbo leva o modelo, e cada
  medição roda duas vezes, porque o resultado varia.

**6. Gate do CI.** O `test_motor_nao_regrediu_na_calibracao` compara a calibração com o
`tools/linha_de_base_motor.json`.
- Tolera **um caso** a mais de erro em cada uma das quatro proporções, nunca dois. O plano previa
  3 p.p., mas com 67 golpes 3 p.p. aceitam dois golpes perdidos (2/67 = 2,99 p.p.) e com 46
  legítimas só um alarme. Em casos, a margem vale igual nas duas classes.
- Se o corpus mudar (outro hash), o gate falha até que alguém regrave com `--gravar-linha-de-base`
  e anote o antes e o depois no diário.
- O gate olha só a calibração porque o CI faz parte do ciclo de ajuste: mostrar o teste a ele
  seria ajustar contra o teste.

**7. Relatório.** Cada rodada gera um `docs/avaliacoes/AAAA-MM-DD-<motor|com-ia>.md`, que nunca
sobrescreve o anterior. O carimbo traz a versão e os cortes das regras, o modelo, o commit (e se
havia alteração local), o SHA-256 do corpus com fim de linha normalizado e a semente. Os erros
aparecem **só pelo id**.

## Limitações declaradas

- **Sintético é mais "limpo" que o real:** sem erro de OCR, sem contexto de conversa, sem golpe que
  ninguém imaginou. O número medido é **otimista**, e o "casos reais" do §1.6 **não fica
  atestado**.
- **Autor e rotulador são a mesma pessoa:** o rótulo não é independente, e quem escreveu o caso já
  sabia a resposta.
- **Viés de autoria:** o Claude escreveu os casos, e um Claude (Haiku) os analisa. O modelo tende a
  reconhecer o estilo da própria família, e a divisão não corrige isso. Por isso existem o campo
  `autor` e o recorte por autor. Os casos com `autor: walter` (modelo em `corpus/para-o-walter.md`)
  são o **teste fora da família**.
- **O corte de 0,85 só pega quase-cópias.** Variações do mesmo golpe escritas com outras palavras
  (os vários Correios, por exemplo) podem ficar uma na calibração e outra no teste. Isso deixa o
  teste **mais fácil do que parece**: ajustar num caso ensina o gêmeo de outro lado. A divisão não
  foi refeita por causa disso, porque refazê-la depois de ver o resultado quebraria o item 3. Os
  casos do Walter, de outra mão, são a resposta parcial.
- **O motor ainda não pontua URL** (Fases 3 e 4): link suspeito sozinho não pesa nada.
- **48 casos de teste dão intervalos largos.** Por exemplo, recall de 28/28 tem IC de 87,9% a 100%.
- Os níveis gravados nas baterias são das regras v1 e v2. O corpus mede de novo com a v3, e nenhum
  número das baterias é reaproveitado.

## Consequências

- **Primeira medição (2026-10-27, regras v3):**
  - O motor sozinho detecta **24,2%** dos golpes (23/95), com precisão de 92,0% e 2 alarmes falsos
    em 66 legítimas, e 46 golpes ficam em score 0. Ele bate a linha de base trivial (10,5%), mas
    passa longe do KPI.
  - Com a IA, no teste, a precisão foi de **93,3%** e o recall de **100%** nas duas rodadas. O KPI
    hoje se apoia na IA, num corpus que a favorece pelo viés de autoria e pelos gêmeos.
- Esta é a medição que o ADR-0005 manda publicar com as duas variantes do MÉDIO. O relatório
  continua publicando as duas.
- Daqui em diante, mudança no motor ou no prompt vem com um relatório antes e outro depois.
  Mudança no corpus regrava a linha de base, com o antes e o depois no diário.
