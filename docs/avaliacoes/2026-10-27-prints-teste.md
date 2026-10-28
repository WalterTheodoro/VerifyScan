# Avaliação dos prints sintéticos — 2026-10-27 22:30

- **Modelo:** `claude-haiku-5-5` · **camada de resolução:** confirmada: 1170x2532 aceita sem redução (`oversized_image: error`), 3841 tokens de entrada na contagem
- **Commit:** `9b88a8f` com alterações locais · **hash do corpus:** `49cb4116284a9d9f` · **semente dos prints:** 20261027
- **Prints:** 20 (Counter({'normal': 20})), todos da divisão `teste`, sintéticos (`tools/gerar_prints.py`). Autores dos casos: {'claude': 20}.

## Leitura

- **Taxa de erro por caractere (CER)**, 20 prints normais lidos: p50 0.000 · p95 0.196 · máxima 0.196 · média 0.024.
- Transcrição sem nenhum erro: 15/20 (75%).
- **Quem mandou cada mensagem** certo em todas as mensagens do print: 20/20 (100%).

| Campo do contexto | Acerto |
|---|---|
| `canal` | 19/20 (95%) |
| `remetente_salvo` | 20/20 (100%) |
| `aviso_do_app` | 20/20 (100%) |
| `primeira_mensagem` | 18/20 (90%) |
| `tem_link_visivel` | 20/20 (100%) |

`canal` só tem resposta certa nos layouts de e-mail e SMS; no chat genérico vale `outro` ou `nao_identificado`, porque o desenho não imita aplicativo nenhum. A transcrição do caso 0035 (injeção) tem um caractere invisível que inverte o texto na tela: a leitura transcreve o que aparece, e a taxa de erro desse print conta isso.

Por variação (CER médio; prints normais):

| Variação | Valor | Prints | CER médio | `remetente_salvo` | `aviso_do_app` | `primeira_mensagem` |
|---|---|---|---|---|---|---|
| layout | chat | 6 | 0.021 | 6/6 (100%) | 6/6 (100%) | 6/6 (100%) |
| layout | email | 4 | 0.088 | 4/4 (100%) | 4/4 (100%) | 4/4 (100%) |
| layout | sms | 10 | 0.000 | 10/10 (100%) | 10/10 (100%) | 8/10 (80%) |
| remetente | numero | 12 | 0.029 | 12/12 (100%) | 12/12 (100%) | 10/12 (83%) |
| remetente | salvo | 8 | 0.016 | 8/8 (100%) | 8/8 (100%) | 8/8 (100%) |
| aviso | nao | 16 | 0.024 | 16/16 (100%) | 16/16 (100%) | 14/16 (88%) |
| aviso | sim | 4 | 0.024 | 4/4 (100%) | 4/4 (100%) | 4/4 (100%) |
| primeira | nao | 8 | 0.000 | 8/8 (100%) | 8/8 (100%) | 6/8 (75%) |
| primeira | sim | 12 | 0.040 | 12/12 (100%) | 12/12 (100%) | 12/12 (100%) |
| tema | claro | 10 | 0.026 | 10/10 (100%) | 10/10 (100%) | 10/10 (100%) |
| tema | escuro | 10 | 0.022 | 10/10 (100%) | 10/10 (100%) | 8/10 (80%) |

## Plano B e injeção

- **Borrados de propósito no plano B** (`ilegivel`): — ().
- **Prints legíveis que caíram no plano B da leitura:** nenhum.
- **Injeção pega pelo motor** (`instrucao_ao_analisador`): —; nível final —.

## Conselho

- **Explicação que cita um aplicativo pelo nome sem a leitura ter identificado o canal** (`outro` ou `nao_identificado`): 0/5 (0%).

## Nível: imagem contra texto do mesmo caso

- **Motor igual:** 20/20 (100%) · **final igual:** 18/20 (90%).
- **Imagem abaixo do texto** (final): t12 (MEDIO→BAIXO), t13 (MEDIO→BAIXO).
- **Imagem acima do texto** (final): nenhum.
- **Golpes em MÉDIO ou ALTO:** imagem 10/10 (100%) · texto 10/10 (100%).
- **Legítimas em MÉDIO ou ALTO (alarme):** imagem 1/10 (10%) · texto 3/10 (30%).

## Tempo e custo

- **Leitura:** p50 1843 ms · p95 2429 ms · máxima 3361 ms (teto 10 s).
- **Análise da IA no caminho de imagem:** p50 2278 ms · p95 2838 ms · máxima 3057 ms (teto 10 s).
- **Total do print** (validação + leitura + motor + IA, sem o registro): p50 4278 ms · p95 4976 ms · máxima 5492 ms (RNF02: < 30 s).
- **Plano B da análise no caminho de imagem:** nenhum.
- **Tokens da leitura:** 121700 de entrada, 3795 de saída · **da análise (imagem):** 79278 / 6247 · **da análise (texto, comparação):** 56910 / 6012.
- **Custo estimado por print** (leitura + análise): US$ 0.00126; **por texto:** US$ 0.00043 (preço de tabela em `tools/testar_ia.py`; estimativa, não fatura).

## Por print

| Print | Caso | Tipo | Rótulo | Layout | Remetente | Aviso | 1ª | Tema | CER | Contexto | Motor img/txt | Final img/txt | Leitura ms | Total ms | Plano B |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| t01 | 0015 | normal | golpe | chat | salvo | nao | sim | claro | 0.000 | 5/5 | BAIXO/BAIXO | ALTO/ALTO | 1925 | 4760 | — |
| t02 | 0031 | normal | golpe | chat | salvo | nao | sim | escuro | 0.126 | 5/5 | BAIXO/BAIXO | ALTO/ALTO | 1843 | 4687 | — |
| t03 | 0114 | normal | golpe | sms | salvo | nao | nao | claro | 0.000 | 5/5 | BAIXO/BAIXO | ALTO/ALTO | 1908 | 4152 | — |
| t04 | 0005 | normal | golpe | sms | salvo | nao | nao | escuro | 0.000 | 5/5 | MEDIO/MEDIO | ALTO/ALTO | 1752 | 4510 | — |
| t05 | 0029 | normal | golpe | email | numero | nao | sim | claro | 0.196 | 5/5 | BAIXO/BAIXO | ALTO/ALTO | 1946 | 4455 | — |
| t06 | 0078 | normal | golpe | sms | numero | nao | sim | escuro | 0.000 | 5/5 | ALTO/ALTO | ALTO/ALTO | 1635 | 4295 | — |
| t07 | 0039 | normal | golpe | chat | numero | nao | nao | claro | 0.000 | 5/5 | ALTO/ALTO | ALTO/ALTO | 1742 | 4038 | — |
| t08 | 0102 | normal | golpe | sms | numero | nao | nao | escuro | 0.000 | 4/5 | ALTO/ALTO | ALTO/ALTO | 1820 | 4167 | — |
| t09 | 0046 | normal | golpe | sms | numero | sim | sim | claro | 0.000 | 5/5 | BAIXO/BAIXO | ALTO/ALTO | 1714 | 4471 | — |
| t10 | 0120 | normal | golpe | email | numero | sim | sim | escuro | 0.037 | 5/5 | BAIXO/BAIXO | ALTO/ALTO | 1897 | 4976 | — |
| t11 | 0170 | normal | legitimo | sms | salvo | nao | sim | claro | 0.000 | 5/5 | BAIXO/BAIXO | BAIXO/BAIXO | 1497 | 3718 | — |
| t12 | 0138 | normal | legitimo | sms | salvo | nao | sim | escuro | 0.000 | 5/5 | BAIXO/BAIXO | BAIXO/MEDIO | 3361 | 5492 | — |
| t13 | 0077 | normal | legitimo | chat | salvo | nao | nao | claro | 0.000 | 5/5 | BAIXO/BAIXO | BAIXO/MEDIO | 2429 | 4278 | — |
| t14 | 0148 | normal | legitimo | sms | salvo | nao | nao | escuro | 0.000 | 5/5 | BAIXO/BAIXO | MEDIO/MEDIO | 1916 | 4740 | — |
| t15 | 0173 | normal | legitimo | email | numero | nao | sim | claro | 0.062 | 5/5 | BAIXO/BAIXO | BAIXO/BAIXO | 1809 | 3946 | — |
| t16 | 0066 | normal | legitimo | chat | numero | nao | sim | escuro | 0.000 | 4/5 | BAIXO/BAIXO | BAIXO/BAIXO | 1557 | 3654 | — |
| t17 | 0070 | normal | legitimo | chat | numero | nao | nao | claro | 0.000 | 5/5 | BAIXO/BAIXO | BAIXO/BAIXO | 2106 | 3884 | — |
| t18 | 0152 | normal | legitimo | sms | numero | nao | nao | escuro | 0.000 | 4/5 | BAIXO/BAIXO | BAIXO/BAIXO | 2208 | 4592 | — |
| t19 | 0160 | normal | legitimo | sms | numero | sim | sim | claro | 0.000 | 5/5 | BAIXO/BAIXO | BAIXO/BAIXO | 1911 | 4052 | — |
| t20 | 0063 | normal | legitimo | email | numero | sim | sim | escuro | 0.059 | 5/5 | BAIXO/BAIXO | BAIXO/BAIXO | 1650 | 3451 | — |
