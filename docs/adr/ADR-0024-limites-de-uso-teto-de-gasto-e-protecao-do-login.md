# ADR-0024 — Limites de uso da IA, teto de gasto e proteção do login

**Data:** 2026-11-14 · **Status:** aceito · **Fase:** 8 (fatia 10) · muda a ordem do ADR-0015 (o
dono passa a ser resolvido antes da IA); complementa o ADR-0013 (login), o ADR-0014 (proxy), o
ADR-0019 (exclusão de conta), o ADR-0020 (IA) e o ADR-0023 (print)

## Contexto

Cada análise chama a API da Anthropic: ~US$ 0,00043 por texto e ~US$ 0,00126 por print (leitura +
análise, quase 3×; medidos no ADR-0023). Não havia limite: qualquer um podia gastar o crédito do
projeto. O login também não limitava tentativas, e cada verificação Argon2id ocupa ~19 MiB: com
512 MB no Render gratuito, umas 25 verificações simultâneas derrubariam o processo.

## Opções consideradas

- Contador **em memória** × **no Postgres**. O Render gratuito dorme depois de 15 min parado, e um
  contador diário em memória zeraria a cada sono. Para a cota e para os cadastros por dia, o
  Postgres. Para as senhas erradas, com janela de 15 min, a memória basta (item 6).
- Ler, conferir e gravar × **UPSERT com limite numa instrução só**. Em três passos, dois pedidos
  simultâneos leem o mesmo total e passam os dois.
- Limitar pelo IP que o backend vê × **IP repassado pelo frontend, com segredo**. O backend fica
  atrás do proxy do Next (ADR-0014) e vê o IP do frontend: um limite por ele juntaria todo mundo.
  Mas o backend também é acessível direto, e qualquer um pode mandar um cabeçalho de IP.
- Guardar o IP × **guardar o HMAC dele**. O IP é dado pessoal; o HMAC com um segredo do servidor
  identifica a mesma conexão sem guardá-la.

## Decisão

**1. Cota diária de IA, em unidades: texto 1, print 3.**
- Sem conta, 5 por dia; com conta, 25. O dia vira à meia-noite de America/Sao_Paulo
  (`app/core/relogio.py`, com o `tzdata` declarado: o Windows não tem banco de fusos e a imagem do
  Render não garante um).
- Valores no `Settings`: `IA_COTA_SEM_CONTA` e `IA_COTA_COM_CONTA`.
- **Custo máximo por pessoa por dia**, pelo custo médio medido no ADR-0023:
  - sem conta, ≈ **US$ 0,0022** (5 textos = US$ 0,00215, ou 1 print + 2 textos = US$ 0,00212);
  - com conta, ≈ **US$ 0,011** (25 textos = US$ 0,01075, ou 8 prints + 1 texto = US$ 0,01051).
  - É custo médio, não pior caso. Quem segura o pior caso é o teto global (item 2).
- **Texto acima da cota:** sai só do motor, com `explicacao_indisponivel: true`,
  `motivo_sem_ia: "cota"` e `aviso_sem_ia` com a frase pronta. A tela não confunde cota com falha
  da IA.
- **Print acima da cota:** 429 com "Você atingiu o limite de prints de hoje. Copie e cole o texto da
  mensagem, que ainda pode ser analisado." Sem leitura não há print.
- **Quanto resta:** `ia_restantes_hoje` volta em toda resposta. A tela mostra "Restam N análises
  com IA hoje" na cor do texto; abaixo de 3, lembra que um print conta como 3.

**2. Teto global de gasto: US$ 1 por dia, somando todo mundo** (`IA_TETO_GASTO_DIARIO_USD`).
- O custo vem dos tokens que a API devolveu (`usage`), com os preços em configuração
  (`IA_PRECO_ENTRADA_USD_POR_MILHAO=0.10`, `IA_PRECO_SAIDA_USD_POR_MILHAO=0.50`).
- O usage é somado por um `ConsumoDaIA` por requisição, logo que a resposta chega e antes de
  interpretá-la. Resposta recusada, cortada ou inválida também foi cobrada e entra na conta; as
  duas chamadas do print também.
- Atingido o teto, todo mundo fica sem IA até a meia-noite: o texto sai do motor, o print sai
  429. A frase é a da cota, sem dizer que é um teto global.
- O log registra uma vez por dia, em WARNING, que o teto foi atingido. A marca `teto_avisado` fica
  no banco, para valer também depois de o processo reiniciar.

**3. Armazenamento: migração 0007, só acrescenta.**
- **`uso_diario`:**
  - colunas `finalidade` (`ia` ou `cadastro`), `chave`, `dia` e `unidades`;
  - chave primária `(finalidade, chave, dia)`;
  - reserva por `INSERT … ON CONFLICT … DO UPDATE SET unidades = unidades + n WHERE unidades + n
    <= limite RETURNING unidades`. Sem linha de volta, foi negada. A trava de linha do
    `ON CONFLICT` faz o segundo pedido ver a soma do primeiro: 20 pedidos simultâneos com cota 5
    dão exatamente 5 (teste de integração, conexões separadas);
  - a chave é `conta:<id>` para quem tem conta e `ip:<HMAC-SHA256 do IP>` para quem não tem;
  - não há id de análise nem hora por pedido: a chave não liga análises anônimas entre si
    (ADR-0006).
- **`gasto_diario_ia`:** o dia, os tokens de entrada e de saída, o custo, as chamadas, as chamadas
  com timeout e a marca do aviso de teto.
- **Prazo de guarda:**
  - o `uso_diario` é apagado pela faxina que já existe (subida e listagem), de anteontem para
    trás; guarda hoje e ontem;
  - **o `gasto_diario_ia` não tem prazo.** Ele não tem dado pessoal: uma linha por dia, só números
    agregados. O prazo de 2 dias existe para o `uso_diario`, que guarda o HMAC do IP. Apagar o
    gasto destruiria a série que mede o gasto não contabilizado (`chamadas_com_timeout`, item 4).
- **Exclusão de conta:** apaga as linhas `conta:<id>` na mesma transação que a conta. A chave é
  texto, sem chave estrangeira, porque também guarda o HMAC do IP. Assim fica de pé a promessa do
  ADR-0019 e de /privacidade de que a exclusão apaga tudo.
- **LGPD:** a base legal é o legítimo interesse de prevenir abuso (Lei 13.709/2018, **art. 7º,
  IX**: "quando necessário para atender aos interesses legítimos do controlador ou de terceiro"),
  com só os dados estritamente necessários (**art. 10, § 1º**). Conferidos no texto do Planalto.
  O HMAC do IP é **dado pseudonimizado**, ainda pessoal, e /privacidade o descreve assim.

**4. Ordem: a cota é conferida e reservada ANTES da chamada à IA.**
- **Texto:** motor (que valida a entrada) → janela da cota → IA → registro e gasto em paralelo.
  Entrada inválida não gasta unidade.
- **Print:** conferência da imagem → janela da cota (3 unidades) → leitura → o miolo do texto.
  Imagem inválida não gasta unidade; leitura que falha gasta.
- **A janela da cota** (`TIMEOUT_COTA_S`, 1,5 s) resolve o dono pela sessão e reserva, num teto só.
  O registro reaproveita o dono e não consulta a sessão de novo. Isso muda a ordem do ADR-0015 —
  lá, o dono só era conhecido no registro.
- **As unidades não voltam** se a IA cair no plano B. A devolução exigiria uma segunda escrita no
  fim da análise, e a chamada que falhou pode ter sido cobrada do mesmo jeito.
- **Banco da cota fora ou acima do teto de tempo:** fail-closed para o dinheiro.
  - O texto sai só do motor, com o plano B comum, sem a frase de cota (que seria falsa) e sem
    "Restam".
  - O print sai 503 com "A leitura de prints não está disponível agora. Copie e cole o texto da
    mensagem." O 429 com a frase de cota seria falso também.

**5. O IP de quem não tem conta.**
- **No frontend** (`frontend/proxy.ts`, que substituiu o `middleware.ts` no Next 16):
  - pega o IP do visitante e o manda em `X-VerifyScan-IP`, com `X-VerifyScan-Segredo`
    (`PROXY_SEGREDO`, a mesma variável nos dois serviços);
  - os dois vão como cabeçalhos do pedido (`NextResponse.next({ request: { headers } })`), que o
    Next aplica antes das rewrites (`resolve-routes.js`). Conferido de ponta a ponta com um
    servidor de eco, e o segredo não volta ao navegador;
  - o que o navegador mandou nesses cabeçalhos é sempre apagado, inclusive no /health.
- **No backend:** confia no IP repassado só quando o segredo confere, com comparação em tempo
  constante (`hmac.compare_digest`). Sem o segredo certo, ignora o cabeçalho.
- **Qual IP: a entrada mais à direita do `X-Forwarded-For`, nos dois serviços.**
  - O Render não documenta o cabeçalho.
  - O único registro está no quadro de sugestões dele
    (feedback.render.com/features/p/send-the-correct-xforwardedfor). Um funcionário escreveu em
    2021 que "a primeira entrada é o IP real"; um teste de março de 2024 na mesma página diz que o
    Render só acrescenta ao que o cliente mandou, sem limpar.
  - Se for assim, a primeira entrada é forjável, e a última, quem pôs foi o Render.
- **Normalização:** IPv6 agrupado por /64 (quem tem um /64 troca de endereço à vontade); IPv4
  escrito como IPv6 volta a ser IPv4.
- **O IP puro nunca é gravado nem logado:**
  - no banco e no limite de login vai o HMAC (`IP_HMAC_SEGREDO`, sem default: com um conhecido, o
    HMAC de um IPv4 se desfaz percorrendo os 2³² endereços);
  - **o log de acesso do uvicorn sai desligado dentro da aplicação.** Medido localmente: o
    uvicorn troca o endereço pelo do `X-Forwarded-For` quando confia no proxy, e o IP forjado
    `203.0.113.250` apareceu no log. Desligar no código não depende de lembrar uma opção no
    comando de start;
  - o caplog confere todos os loggers em DEBUG.
- **Os dois segredos são obrigatórios.** O backend nem sobe sem eles, e o erro não mostra o valor
  recebido (`hide_input_in_errors`). O build de produção do frontend quebra sem `PROXY_SEGREDO`.

**6. Proteção do login.**
- **Semáforo no Argon2** (`ARGON2_SIMULTANEOS=2`): no máximo 2 cálculos ao mesmo tempo no
  processo. As outras esperam até o teto da autenticação (5 s) e, depois dele, recebem 503 com
  "Muitas pessoas estão entrando agora. Tente de novo em alguns segundos." Só a espera tem teto;
  o cálculo continua fora de timeout (ADR-0013).
- **Senhas erradas no login, na troca de senha e na exclusão:** 10 por conta e 30 por IP em
  15 min, em janela deslizante. Passou: 429 com "Muitas tentativas. Espere alguns minutos e tente
  de novo."
  - **Chave da conta:** o HMAC do e-mail normalizado. Vale também para e-mail que não tem conta,
    então o 429 não revela quem está cadastrado. As três operações dividem a mesma chave.
  - **Momento da conferência:** antes do banco e do Argon2.
  - **Acerto:** zera a conta, não o IP. É o que recomenda a NIST SP 800-63B-4, §3.2.2 "Rate
    Limiting (Throttling)": o verificador SHALL limitar as falhas consecutivas (até 100) e SHOULD
    desconsiderar as anteriores depois de uma autenticação certa.
  - **Fica em memória** (`app/services/tentativas.py`), e é aceitável porque a janela (15 min,
    `le=15`) não passa do tempo que o Render leva para dormir parado: um reinício por ociosidade
    só apaga falhas que já tinham saído da janela, e quem ataca mantém o processo acordado.
  - **Memória limitada:** no máximo 10 mil chaves. A do IP é atualizada a cada falha e sai por
    último.
- **Cadastro:** 5 contas por IP por dia, no `uso_diario` (`finalidade='cadastro'`), para ninguém
  criar contas em série e multiplicar a cota de 25.
  - Conferido depois das validações e antes do Argon2.
  - E-mail já cadastrado também gasta, porque a recusa só vem no banco.
  - Frase do 429: "Muitas contas foram criadas a partir desta conexão hoje. Tente de novo amanhã."
    "Alguns minutos" seria falso num limite diário.

**7. Os tetos `le=` das cotas e do gasto barram engano, não congelam a operação.**
- Valores: cota sem conta até 200, com conta até 500, teto de gasto até US$ 20, janela da cota até
  5 s.
- No Poster + Demo Day, todos os visitantes estarão na mesma rede, com o mesmo IP público: a sala
  esgotaria 5 unidades em minutos. A cota precisa poder subir naquela data sem deploy de código.
- O limite real de gasto é o teto global, e ele também precisa ser ajustável para eventos.
- Os limites de segurança (login, cadastro, Argon2) seguem a regra antiga: só baixam.

## Orçamento de tempo (invariante 8, RNF02 < 30 s)

Tetos, não medições. A janela da cota faz 3 ou 4 consultas: a sessão, o gasto do dia, o UPSERT e,
se a reserva for negada, a leitura do uso. O gasto é gravado em paralelo com o registro, no teto
dele.

| Caminho | Antes | Agora |
|---|---|---|
| Texto, hoje | 0,3 + IA 15 + registro 2 ≈ 17,3 s | 0,3 + **cota 1,5** + 15 + 2 ≈ **18,8 s** |
| Texto, desenho completo | máx(0,3; RDAP 3; reputação 5) + 15 + 2 ≈ 22 s | ≈ 22 s: a cota roda junto de RDAP e reputação |
| Print, hoje | imagem 0,2 + leitura 10 + 0,3 + análise 10 + 2 ≈ 22,5 s | 0,2 + **1,5** + 10 + 0,3 + 10 + 2 ≈ **24 s** |
| Print, desenho completo | 0,2 + 10 + 5 + 10 + 2 ≈ 27,2 s | 0,2 + **1,5** + 10 + 5 + 10 + 2 ≈ **28,7 s** |

**`TIMEOUT_COTA_S` aceita até 5 s pelo `Settings`, mas acima de ~2,8 s o pior caso do desenho
completo do print passa dos 30 s do RNF02** (0,2 + t + 10 + 5 + 10 + 2). É a única exceção ao "os
tetos só podem baixar" da invariante 8: o default fica em 1,5 s, e a folga existe para um banco
lento. **A fatia de reputação externa precisa refazer esta conta**: hoje, sem reputação, o limite
da janela é ~7,5 s.

Um Neon acordando em mais de 1,5 s deixa a análise sem IA, com o plano B comum. O GET a /health ao
abrir a página (ADR-0017) faz `SELECT 1` e costuma acordá-lo antes do envio.

## Consequências

- **Risco de travamento:** quem sabe um e-mail trava aquela conta por 15 minutos com 10 senhas
  erradas, mesmo sem saber a senha. É o custo conhecido de limitar por conta, e é preferível a não
  limitar:
  - sem limite, a senha de qualquer conta pode ser adivinhada sem parar, e cada tentativa ainda
    gasta ~19 MiB de Argon2;
  - o travamento é temporário e não revela nada (o e-mail sem conta trava igual): o dono só
    precisa esperar 15 minutos;
  - a NIST aceita até 100; 10 é mais restrito, de propósito, para um público que reutiliza senha.
- **Quem está atrás do mesmo NAT divide a cota sem conta:** uma escola, um evento, uma operadora
  com CGNAT. A saída é entrar com conta (25 por dia, chave própria) ou aumentar
  `IA_COTA_SEM_CONTA` naquela data.
- **O limite por IP é de melhor esforço.** O comportamento do `X-Forwarded-For` no Render não é
  documentado, e quem troca de rede troca de cota. **A garantia do dinheiro é o teto global.**
  - Verificação depois do deploy, sem logar IP: 5 análises sem conta e a 6ª com um
    `X-Forwarded-For` forjado precisam continuar sem IA; num 4G, a cota precisa ser outra.
- **Gasto não contabilizado:**
  - chamada cortada pelo nosso teto de tempo não devolve usage e fica fora do custo, mas é
    contada em `chamadas_com_timeout`. O gasto que escapa é estimável: chamadas com timeout ×
    (custo ÷ chamadas);
  - o teto é conferido antes da chamada e o custo é somado depois, então pedidos simultâneos podem
    passar do teto, no máximo (pedidos em voo) × (custo de uma chamada).
- **Unidades não voltam** quando a IA cai no plano B nem quando a leitura do print falha.
- **O deploy zera as tentativas de senha**, que ficam em memória. Um reinício por ociosidade, não.
- **O log de plataforma do Render** guarda o IP e o horário de cada acesso, fora do nosso
  controle; /privacidade já dizia isso.
- **O backend desta fatia não pode ir ao ar sem o frontend e o `PROXY_SEGREDO` dos dois lados.**
  Sem o IP repassado, todos os visitantes sem conta cairiam no IP do frontend: uma cota de 5 para
  todos, e 30 senhas erradas de qualquer um travariam o login de todos. Por isso o build do
  frontend quebra sem o segredo.
- **O `alembic upgrade` do build do Render lê o `Settings`:** os dois segredos precisam estar no
  painel antes do merge.
