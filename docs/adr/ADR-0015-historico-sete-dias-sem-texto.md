# ADR-0015 — Histórico: 7 dias, sem texto, desvinculação

**Data:** 2026-10-01 · **Status:** aceito · **Fase:** 8 (fatia 4) · complementa o ADR-0006

## Contexto

O RF12 pede histórico para o usuário autenticado. O §7.1 do RFC guarda o "Texto enviado" de forma
"Permanente (somente usuários autenticados)", e o §2.6 promete não armazenar conteúdo de terceiros.
Toda mensagem suspeita tem dado de terceiro. O ADR-0006 resolveu o anônimo e o OCR e deixou o
autenticado em aberto (achado 9, PARCIAL). Esta fatia liga a análise à conta e fecha essa decisão.

## Opções consideradas

- Guardar o texto: íntegra × trecho × **nada**.
- Validade do vínculo: permanente × **janela de 7 dias** × apagar a análise ao vencer.
- Limpeza: agendador × **oportunista, sem agendador**.
- Onde consultar a sessão na análise: dependência com 2 s próprios antes da análise × os 5 s da
  autenticação × **dentro do teto do registro, depois do resultado**.
- Como a tela sabe que a análise foi salva: consultar `/api/auth/eu` × cabeçalho HTTP × **campo
  aditivo no corpo**.

## Decisão

**1. Sem texto.** O histórico não guarda a mensagem nem trecho dela. A consulta se reconhece pela
data e hora, pelo nível e pelos fatores, que já são templates do `regras.yaml` (ADR-0004). O achado
9 passa a RESOLVIDO.
- *Evolução futura, não implementada:* um trecho do início da mensagem, só com opt-in por análise,
  mascarado pelos detectores de PII de `tools/pii.py`, com validade de 30 dias.
- *Custo de estar errado:* a pessoa pode não reconhecer uma análise só pela data e pelos fatores. O
  custo do contrário seria guardar dado de terceiro sem base legal clara. Acrescentar o trecho
  depois é migração aditiva; apagar texto já guardado não desfaz o vazamento.

**2. Vínculo.** A migração 0003, aditiva, acrescenta `analises.usuario_id` (UUID, nullable, FK para
`usuarios.id` com `ON DELETE CASCADE`) e o índice `(usuario_id, created_at)`. A análise anônima
continua com `NULL`.
- *Custo de estar errado:* o CASCADE apaga as análises vinculadas junto com a conta. É o que o Gate
  8 pede. As desvinculadas, que já não têm dono, ficam como auditoria anônima.

**3. Registrar com dono, sem a análise esperar pela conta.**
- A rota só **lê** o cookie (`ler_token_de_sessao`) e não faz I/O.
- O orquestrador analisa primeiro. Depois, dentro **do mesmo** `asyncio.timeout(TIMEOUT_PERSISTENCIA_S)`
  do registro, resolve o dono pelo token e grava:
  - sessão válida: grava com `usuario_id`;
  - sem cookie, sessão inválida ou vencida: grava anônima;
  - erro na consulta: grava anônima, com WARNING;
  - teto estourado: não grava nada, como hoje, com WARNING.
- Por que dentro do registro: a análise não precisa saber quem é a pessoa; só o registro precisa. O
  resultado nunca espera pela sessão, o pior caso continua em ≈ 17 s e a **invariante 8 não muda**.
  Com o Neon acordando, a espera acontece uma vez só, e não duas.
- Descartadas:
  - **dependência com 2 s próprios antes da análise:** soma uma etapa em série (≈ 19 s) e faz o
    resultado esperar pelo banco;
  - **reaproveitar os 5 s da autenticação:** ≈ 22 s, e uma falha de conta atrasaria a resposta de
    quem está diante de um golpe.
- A resposta de `POST /api/analises` ganha `salva_no_historico: bool`, true só quando gravou com
  `usuario_id`.
  - É campo aditivo: o frontend atual ignora campos novos.
  - Um cabeçalho HTTP esconderia a informação fora do schema, sem tipo e sem aparecer no OpenAPI.
  - A home não consulta `/eu` para isso.
- *Custo de estar errado:* se o teto cortar durante o `COMMIT`, o servidor pode concluí-lo (ADR-0012).
  A análise fica no histórico e a tela diz "Não conseguimos salvar". É o erro do lado seguro: a
  pessoa acha a análise depois e pode apagá-la.

**4. Janela de 7 dias** (`HISTORICO_DIAS`, default 7), pelo relógio do banco (ADR-0012).
- A listagem mostra só as análises da própria conta com `created_at > now() - janela`.
- Depois da janela, a análise é **desvinculada** (`UPDATE … SET usuario_id = NULL`) e fica idêntica a
  uma anônima do ADR-0006.
- A desvinculação é oportunista, sem agendador: roda na subida do processo (lifespan) e a cada
  listagem, com o teto do registro. Se falhar, só gera log. Na leitura, nada fora da janela aparece,
  rode ela ou não.
- *Custo de estar errado:* a desvinculação física só acontece no primeiro uso depois do vencimento.
  Num serviço que dorme, uma análise pode ficar ligada no banco por mais que 7 dias, sem aparecer na
  tela. O Neon guarda 6 h de histórico de restauração, então o vínculo pode sobreviver nesse
  intervalo também. Um agendador custaria um serviço sempre acordado, contra a regra do ADR-0011.

**5. Rotas**, todas exigindo login (`obter_usuario_atual`; sem sessão, 401):
- `GET /api/historico` devolve `{dias, analises[]}`, a mais recente primeiro, até 200, com os
  fatores por `selectinload`;
- `DELETE /api/historico/{id}` responde 204. Análise inexistente, de outra pessoa ou com id inválido
  recebem **o mesmo 404**, que não revela se ela existe;
- `DELETE /api/historico` responde 204;
- `GET /api/conta` devolve `{nome, email, criado_em}`.

Apagar é `DELETE` de verdade, e os indicadores vão junto pelo CASCADE da 0001. Os erros estão
declarados no OpenAPI.
- *Custo de estar errado:* sem paginação, 200 é o teto. Em 7 dias de uso pessoal isso não chega.

**Timeouts, pelo modo de falha** (a regra do ADR-0013):
- o que a pessoa pediu (listar, apagar, `/api/conta`) usa `TIMEOUT_AUTENTICACAO_S` e responde 503;
- a faxina e o registro usam `TIMEOUT_PERSISTENCIA_S` e só geram log.

Não entrou variável de timeout nova.

## Consequências

- A errata (item 12) troca a linha "Texto enviado" do §7.1.
- O aviso de privacidade passa a cobrir o art. 9º da LGPD, incluindo o vínculo de 7 dias.
- O histórico só existe para quem fez a análise logado. Uma análise anônima nunca é reivindicada
  depois, porque não há como provar de quem ela é.
