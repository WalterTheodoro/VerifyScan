# ADR-0019 — Trocar a senha, excluir a conta pela tela e a faxina das sessões vencidas

**Data:** 2026-10-26 · **Status:** aceito · **Fase:** 8 (fatia 5) · complementa os ADR-0013 e ADR-0015

## Contexto

O ADR-0013 deixou de fora a troca de senha e a exclusão da conta pela tela. A exclusão era feita
pelo contato do aviso de privacidade, e o banco já estava pronto para ela (os CASCADE).

Em 26/10, uma consulta ao Neon achou **5 sessões vencidas paradas**. O ADR-0013 só apaga as
vencidas de uma conta quando a própria pessoa entra de novo, então as de quem nunca mais volta
ficam no banco para sempre. O próprio ADR-0013 registrou essa consequência ("até uma limpeza
global, que não existe ainda").

O público divide o celular com a família, e o frontend trata qualquer 401 como "deslogado"
(ADR-0017 §3).

## Opções consideradas

- Senha errada numa ação de quem já está logado: **401** × **400**.
- Sessões depois de trocar a senha: manter todas × derrubar todas × **derrubar as outras e manter
  a deste aparelho**.
- Excluir: só com a sessão × **com a sessão e a senha**.
- Faxina das sessões: agendador × **a mesma faxina oportunista do ADR-0015**.

## Decisão

**1. `POST /api/conta/senha` `{senha_atual, nova_senha}`**, exige login e responde 204.
- A nova senha segue as regras do cadastro: de 8 a 128 caracteres, sem regra de composição
  (ADR-0013 §5). Se for igual à atual, a resposta é 422 com "A nova senha precisa ser diferente da
  atual.".
- A senha atual é conferida com Argon2id numa thread, fora do teto de tempo (ADR-0013 §6), pelo
  mesmo caminho do login (`buscar_credenciais`).
- O hash novo é gravado e **todas as outras sessões da conta são apagadas, numa transação só**.
  - Quem troca a senha por desconfiança quer tirar o acesso de quem mais estiver logado, sem ter de
    entrar de novo no aparelho onde está.
  - Em duas transações, um timeout entre elas deixaria a senha trocada e o aparelho perdido ainda
    logado.
- **Senha atual errada: 400 "A senha atual não confere.", nunca 401.** A sessão continua válida,
  e um 401 faria a tela trocar tudo por "Entrar" (ADR-0017 §3).

**2. `POST /api/conta/excluir` `{senha}`**, exige login.
- Com a senha errada, a resposta é 400, e nada some. A frase é "A senha não confere.", porque ali
  o campo se chama "Sua senha" (correção de 27/10; a frase vem do service, que sabe qual senha
  pediu, e a rota segue só mapeando o tipo para o status).
- Com a senha certa, `DELETE FROM usuarios`. As sessões, as análises ligadas (com o texto,
  ADR-0018) e os indicadores vão pelos `ON DELETE CASCADE` das migrações 0001, 0002 e 0003: quem
  apaga é o banco. A resposta é 204 com o cookie limpo (`Max-Age=0`, os mesmos atributos da
  gravação).
- **Por que pedir a senha:** no celular da família, sessão aberta sozinha não basta para apagar a
  conta e o histórico de alguém.
- **Por que POST, e não DELETE:** o pedido leva a senha no corpo, e DELETE com corpo é mal suportado
  por proxies.
- Se a conta sumir entre a checagem da sessão e a ação, a resposta é 401, como em `/api/conta`.

**3. Faxina das sessões vencidas.** A faxina do ADR-0015 (na subida do processo e a cada listagem
do histórico) passa a rodar também `DELETE FROM sessoes WHERE expira_em <= now()`, de todas as
contas.
- `<= now()` é o complemento exato do `> now()` de quem autentica: só some o que já não
  autentica.
- Os dois passos dividem **um teto só**, `TIMEOUT_PERSISTENCIA_S`. A listagem não espera mais do
  que esperava antes. Se o primeiro passo falhar, o segundo fica para a próxima vez.
- Estourar o teto ou falhar só vira log, com o tipo da exceção.

**4. Timeouts e erros.**
- As rotas novas usam `TIMEOUT_AUTENTICACAO_S` e respondem 503 quando ele estoura, como as de
  autenticação.
- Os erros estão declarados no OpenAPI (`api/erros.py`, `ERRO_400_SENHA`).
- As rotas ficam em `api/gestao_conta.py`, separadas de `api/conta.py`, que só lê. Estas mexem na
  credencial, nas sessões e no cookie.

**5. Frontend.** Em "Meus dados":
- **"Trocar senha":** os campos "Senha atual" e "Nova senha", com o mínimo de 8 visível antes.
  Depois de trocar, o aviso "Senha trocada. Você saiu das outras sessões abertas." e os campos
  limpos.
- **"Excluir minha conta":** a confirmação abre no próprio quadro, com o foco em "Cancelar" e o
  campo da senha. Depois de excluir, a home mostra "Sua conta foi excluída.".
- **O aviso da exclusão vai por `sessionStorage`** (`vs_conta_excluida`), gravado antes da
  navegação e apagado quando aparece, **nunca pela URL**. Qualquer pessoa poderia montar um link
  com `?conta=excluida` e mostrar a frase a quem está logado, o que, num site sobre golpes,
  assusta. Sem `sessionStorage`, o aviso não aparece.

## O que ficou de fora

- **Rate limit** nestas rotas, pelo mesmo motivo da fatia 2: sem Redis, o custo do Argon2 limita a
  cerca de 4 tentativas por segundo por processo. As duas rotas exigem uma sessão válida antes de
  qualquer tentativa de senha, o que já restringe quem pode tentar.
- **Recuperação de senha por e-mail.** Exige verificação de e-mail e um provedor de envio, que o
  projeto não tem. Quem esquece a senha ainda pode pedir a exclusão pelo contato.

## Custo de estar errado

- **401 na senha errada** faria a pessoa logada ver "Entrar" por ter errado uma letra e achar que
  perdeu a conta.
- **Sem pedir a senha para excluir**, qualquer pessoa com o celular na mão apagaria o histórico de
  outra.
- **O custo da escolha feita:** quem esqueceu a senha não consegue nem trocá-la nem excluir a
  conta pela tela. O contato do aviso de privacidade continua sendo o caminho.
- A faxina só roda quando o processo está acordado. Num serviço que dorme, sessões vencidas podem
  ficar no banco até a próxima subida ou listagem, mas nunca autenticam (o `> now()` da consulta
  vale sempre).
