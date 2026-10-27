# Corpus rotulado

Base de mensagens usada para **medir** o motor de risco, e o motor com a IA. É ela que sustenta o
KPI do RFC: número de precisão só vale se vier do script de avaliação sobre este corpus
(`uv run python -m tools.avaliar_corpus`, ADR-0005 e ADR-0021).

> **Status: 161 casos sintéticos** (95 golpes, 66 legítimas), divisão fixa: 113 casos na
> calibração e 48 no teste. Ainda **sem mensagens reais**. A coleta de mensagens de pessoas espera
> a resposta da coordenação sobre o comitê de ética (pendência no `docs/diario.md`).

## Por que sintético (ADR-0021)

A pendência do comitê de ética vale para mensagens **reais** de familiares, colegas e caixas de
spam. As mensagens sintéticas foram escritas para teste e não têm dado de ninguém, por isso entram
agora. Elas vêm das baterias 1 e 2 de testes no navegador, das amostras do `tools/testar_ia` e de
casos novos. A origem de cada uma fica no `observacoes`.

**Limitação:** o sintético é mais "limpo" que o real, então o número medido é **otimista** e não
atesta o "casos reais" do §1.6. Quem escreveu é quem rotulou. E os casos com `autor: claude` foram
escritos pela mesma família de modelo que a IA do produto usa (viés de autoria), por isso as
métricas saem também por autor. O ADR-0021 lista o resto.

## Formato

Um arquivo YAML por caso em `casos/`, com o nome `NNNN-slug.yaml`:

```yaml
id: '0001'                      # entre aspas, senão o YAML lê o inteiro 1; bate com o nome do arquivo
conteudo: |-
  Correios: seu pacote está retido ... https://correios-rastreio.example/taxa
rotulo: golpe                   # golpe | legitimo — caso ambíguo não entra
fonte: sintetico
autor: claude                   # claude | walter
padrao: "falsa taxa dos Correios por SMS (alertas públicos dos Correios)"   # opcional
canal: sms                      # sms | whatsapp | email | notificacao | print
grupo: correios-taxa            # opcional: só em quase-duplicatas
data: 2026-10-27
observacoes: "bateria 1, caso A01; valores fictícios"
divisao: calibracao             # escrito pelo sorteio, nunca à mão
```

O `padrao` nomeia o **tipo** de alerta público em que o caso se baseia (Febraban, Correios,
gov.br…). Nada de texto copiado de terceiros.

## Divisão: calibração e teste

```powershell
cd backend
uv run python -m tools.sortear_divisao
```

Semente fixa (20261027), 30% de cada rótulo vai para o teste, e um `grupo` cai inteiro do mesmo
lado. O script só escreve `divisao:` em caso que ainda não tem, e nunca muda uma existente: caso
novo entra no sorteio, os antigos ficam onde estão.

**Regra:** ajuste de peso, padrão ou prompt olha só a **calibração**. O **teste** só serve para
relatar.

## Anonimização: obrigatória antes do commit

Substituir por placeholder, sem exceção: `[NOME]`, `[TELEFONE]`, `[EMAIL]`, `[CPF]`,
`[CHAVE_PIX]`, `[CONTA]`, `[AGENCIA]`, `[RASTREIO]`, `[PLACA]`. Link vai para o domínio reservado
`.example`. Marca e órgão (Correios, INSS, nome de banco) ficam, porque são o sinal de
personificação.

O `backend/tests/test_corpus.py` reprova, no CI, qualquer caso com padrão de CPF, telefone ou
e-mail (ADR-0006). Valor em reais só passa em caso com `fonte: sintetico`, onde ele é fictício e
faz parte do golpe ("taxa de R$ 12,90"). Em caso real, ele também vira placeholder. O mesmo teste
confere o formato, que não haja mensagem repetida depois de normalizar e que nenhum grupo fique
dividido.

## Casos do Walter

`para-o-walter.md` é o modelo para 20 casos escritos à mão (10 golpes, 10 legítimas). Eles entram
com `autor: walter`, a mesma anonimização e o mesmo sorteio, e servem de teste fora da família de
modelo que escreveu o resto.

## Proveniência

Cada caso registra `fonte`, `autor`, `data` e a origem em `observacoes`. A banca pode perguntar de
onde veio a base, e "de vários lugares" não é resposta.
