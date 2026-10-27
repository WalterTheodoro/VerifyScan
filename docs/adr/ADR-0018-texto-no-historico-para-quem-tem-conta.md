# ADR-0018 — A mensagem no histórico de quem tem conta, pelos 7 dias da janela

**Data:** 2026-10-26 · **Status:** aceito · **Fase:** 8 (fatia 5) · substitui o item 1 do ADR-0015

## Contexto

O ADR-0015 decidiu um histórico sem texto: a pessoa reconheceria a análise pela data, pelo nível e
pelos fatores. Em uso, isso não basta. Duas análises do mesmo dia com o mesmo nível são
indistinguíveis, e quem volta ao histórico quer rever **o que** recebeu, não só o veredito.

O RFC pede o contrário do ADR-0015: o §5.5 tem `Analise.texto_input`, e o §7.1 guarda o "Texto
enviado" de forma "Permanente (somente usuários autenticados)". Ao mesmo tempo, o §2.6 promete não
armazenar conteúdo de terceiros, e toda mensagem suspeita tem dado de terceiro (achado 9).

## Opções consideradas

- **Nunca guardar**, como no ADR-0015. Perde a identificação da análise.
- **Caixa de consentimento a cada análise.** Descartada por decisão do Walter: é pouco prática
  para quem tem baixo letramento digital, e o dado some em 7 dias de qualquer jeito.
- **Trecho mascarado** pelos detectores de `tools/pii.py`. Perde precisão: o pedaço que a pessoa
  reconheceria (o valor, o nome da loja) é justamente o que a máscara tira.
- **Guardar sempre para quem está logado, só pela janela do histórico.**

## Decisão

**1. Guardar a mensagem inteira de quem está logado, sem caixa de seleção.**
- O texto é gravado sempre que o registro resolve o dono (ADR-0015 §3). Análise anônima continua
  sem texto (ADR-0006), e OCR nunca guarda texto.
- `POST /api/analises` não ganha campo no pedido. A resposta ganha `texto_salvo: bool`
  (aditivo), que só é true quando a análise foi gravada com dono **e** com texto.
- `GET /api/historico` devolve `texto` em cada item (`null` nas análises anteriores a este ADR).

**2. O banco garante a regra** (migração 0004, aditiva e escrita à mão):
- coluna `analises.texto_input TEXT NULL`, com o nome da §5.5;
- `ck_analises_texto_so_com_dono`: `texto_input IS NULL OR usuario_id IS NOT NULL`;
- `ck_analises_texto_ate_5000`: `char_length(texto_input) <= 5000`.

O `RegistroAnalise` repete as duas primeiras regras no `__post_init__`: texto sem dono, ou texto
de entrada que não é `texto`, levanta `ValueError` antes de chegar ao banco.

**3. O texto vive exatamente a janela do histórico.**
- A desvinculação dos 7 dias faz, no mesmo UPDATE, `usuario_id = NULL` e `texto_input = NULL`. O
  CHECK recusaria tirar o dono e deixar o texto.
- Apagar uma análise, apagar o histórico ou excluir a conta (ADR-0019) apaga a linha, com o texto
  junto. A FK `analises.usuario_id` é `ON DELETE CASCADE` (0003), e o teste de integração da
  exclusão confere a pré-condição: a análise apagada tinha texto.

**4. Limite travado em 5000.** `TEXTO_MAX_CARACTERES` passa a ter `le=5000`. Com um limite maior,
toda análise logada acima de 5000 caracteres seria aceita e perderia o registro em silêncio, no
CHECK. Assim, o processo nem sobe. Subir o limite passa a exigir migração e configuração juntas.

**5. O texto nunca vai para log nem para mensagem de erro.**
- Os logs do registro e da faxina levam só o tipo da exceção (ADR-0012).
- **`hide_parameters=True` no engine** (`core/db.py`). Com o texto no banco, o INSERT da análise
  logada carrega a mensagem. Sem essa opção, o SQLAlchemy escreve os parâmetros no seu log de
  INFO e dentro do texto de qualquer `StatementError`. Um teste unitário confere a opção, e o
  engine dos testes de integração usa a mesma.
- O teste de integração força o pior caso: um INSERT real que viola um CHECK, cujo erro do Postgres
  traz a linha recusada inteira ("Failing row contains …"). Gravar, listar, desvincular e falhar
  ao gravar, capturados em INFO, não deixam nenhum trecho da mensagem no log.
- Em DEBUG, o próprio SQLAlchemy escreve as linhas que lê do banco. Nenhum processo do projeto
  liga esse nível no logger `sqlalchemy`.

**6. A tela avisa antes de enviar.**
- Na home, só para quem está logado, abaixo do botão: "Como você está na sua conta, esta mensagem
  fica no seu histórico por 7 dias.", com o link "Saiba mais" para o aviso de privacidade.
- Depois do resultado, com `texto_salvo`: "Esta análise foi salva no seu histórico por 7 dias, com
  a mensagem."
- O cartão da home "Sua mensagem não fica guardada" passou a "Sem conta, sua mensagem não fica
  guardada", com a frase sobre os 7 dias.

**7. As URLs continuam fora do banco.** O item do histórico mostra o mesmo resultado da home
(placa, resumo, "O que fazer" e fatores), menos a lista "Links que aparecem na mensagem". A forma
canônica preserva a query string (ADR-0009), e o ADR-0012 a deixou fora do banco. Os links seguem
visíveis, como texto, dentro de "Você colou:".

## Base legal

É a **execução do serviço que a pessoa contratou ao criar a conta** (LGPD, art. 7º, V), e não o
consentimento (art. 7º, I). O histórico com a mensagem é a funcionalidade da conta. Para essa base
valer, a pessoa precisa saber antes:
- pela frase visível acima do envio (item 6);
- pelo aviso de privacidade, que diz o que é guardado, por quanto tempo e como apagar.

Frente ao RFC, a versão final é mais restrita que o §7.1:
- guarda só para quem está logado;
- só por 7 dias, e apaga no fim da janela;
- apaga junto com a conta;
- e cada análise pode ser apagada a qualquer momento.

**Limitação declarada:** o conflito com o §2.6 continua. A mensagem guardada contém dado de
terceiro (nome, telefone, valor de quem a enviou). A mitigação é o prazo curto e a exclusão a
qualquer momento, não a ausência do dado.

## Limitações conhecidas

- **O log do próprio Postgres.** Se um CHECK da 0004 for violado, o servidor Postgres (o Neon, em
  produção) pode registrar no log dele a linha recusada, com o texto. Esse log fica fora do nosso
  controle. Isso só acontece por defeito: o `RegistroAnalise` recusa texto sem dono antes, e a
  entrada acima de 5000 caracteres é recusada pelo service antes de chegar ao registro.
- **Backups do Neon.** O histórico de restauração de 6 h pode conter um texto já apagado nesse
  intervalo, como o vínculo do ADR-0015.

## Custo de estar errado

- **Num vazamento do banco**, ficam expostos os textos dos últimos 7 dias de todas as pessoas
  logadas, com o dado de terceiros que eles carregam. Antes deste ADR, o vazamento expunha só
  níveis e fatores.
- **A banca pode cobrar a falta de escolha por análise.** A falta da caixa é uma decisão
  consciente, registrada aqui com o motivo: o aviso visível antes do envio e o prazo curto
  substituem a caixa para o público do produto.
- Voltar atrás é barato: parar de gravar é uma linha no orquestrador, e o texto existente some
  sozinho em 7 dias.

## Consequências

- Errata, item 12: o texto passa a ser guardado para o usuário autenticado, por 7 dias, com aviso
  visível; o anônimo nunca.
- Achado 9: resolvido por ADR-0006 + ADR-0015 + ADR-0018.
- ADR-0015: o item 1 está substituído por este ADR; os itens 2 a 5 continuam valendo.
