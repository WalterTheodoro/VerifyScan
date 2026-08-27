# Corpus rotulado

Base de mensagens usada para **medir** o motor de risco. É ela que sustenta o KPI de precisão do
RFC — número de precisão só vale se vier do script de avaliação sobre este corpus
(`uv run python -m tools.avaliar_corpus`).

> **Status: vazio.** O corpus é entrega da Fase 2 do `docs/plano-de-execucao.md`. Este arquivo
> existe desde a Fase 0 para que nenhum caso entre sem proveniência e sem anonimização.

## Antes de adicionar o primeiro caso

Há uma pendência bloqueante registrada em `docs/diario.md`: confirmar com a coordenação do curso
se a coleta exige submissão ao comitê de ética e qual registro de consentimento é aceito. Os casos
vêm de mensagens de familiares, colegas e caixas de spam pessoais — são dados de pessoas, num
repositório cujo histórico não se apaga (ADR-0006).

## Formato

Um arquivo YAML por caso em `casos/`:

```yaml
id: 0001
conteudo: |
  Sua conta sera suspensa. Regularize em bit.ly/xxxx
rotulo: golpe        # golpe | legitimo
fonte: whatsapp-familiar
data: 2026-09-01
observacoes: encaminhada por terceiro; remetente desconhecido
```

## Anonimização — obrigatória antes do commit

Substituir por placeholder, sem exceção: nomes próprios, telefones, CPF/CNPJ, e-mails, valores
monetários, números de conta e agência, e qualquer URL que identifique uma pessoa. O que importa
para a heurística é a **forma** da mensagem, não o dado real.

Um teste do CI reprova qualquer arquivo em `casos/` que contenha padrão de CPF, telefone, e-mail
ou valor monetário fora do formato de placeholder (ADR-0006). O gate é automático porque um commit
com dado real de um familiar em repositório público não se desfaz.

## Proveniência

Cada caso registra `fonte` e `data`. A banca pode perguntar de onde veio a base — e "de vários
lugares" não é resposta.
