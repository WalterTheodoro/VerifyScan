# ADR-0013 — Autenticação: Argon2id, sessão opaca e cookie first-party

**Data:** 2026-10-01 · **Status:** aceito · **Fase:** 8 (fatia 2)

## Contexto

A fatia 2 da Fase 8 põe cadastro, login, logout e "quem sou eu" no backend. O RFC fixa "senha
criptografada (bcrypt)" (RNF03) e "tokens de sessão JWT" (§7). Quatro restrições pesam contra o
texto do RFC:

- o deploy é o Render gratuito, com 512 MB e 0,1 CPU;
- o Gate 8 exige excluir a conta sem sobrar nada;
- o frontend e o backend ficam em subdomínios de `onrender.com`;
- o público tem baixo letramento digital.

## Opções consideradas

- Hash de senha: bcrypt × **Argon2id** (argon2-cffi) × passlib (sem manutenção).
- Sessão: JWT × **token opaco, com o hash dele no banco**.
- Cookie: no domínio do backend × **first-party no domínio do frontend, sem `Domain`**.
- Validação: 422 padrão do FastAPI × **service com mensagens em pt-BR**.

## Decisão

**1. Senha com Argon2id**, com os parâmetros mínimos da OWASP escritos no código:
`time_cost=2`, `memory_cost=19456` (19 MiB) e `parallelism=1`.
- **Os defaults do argon2-cffi (64 MiB, p=4) não cabem no plano.** Medido em 1 vCPU:

  | Algoritmo e parâmetros | Tempo por hash |
  |---|---|
  | Argon2id OWASP | 23,6 ms |
  | bcrypt custo 12 | 301,7 ms |
  | default do argon2-cffi | 142,5 ms |

  Em 0,1 CPU, a estimativa por proporção de cota é cerca de 10× esses tempos.
- **Hash e verificação rodam numa thread** (`asyncio.to_thread`). No event loop, cada login
  congelaria todas as requisições do processo.
- **Rehash.** Depois de um login certo, se `check_needs_rehash` for verdadeiro, o hash é regravado.
- **Hash de mentira.** O processo gera, na subida, o hash de uma senha que ninguém conhece. Login
  com e-mail inexistente verifica contra ele, para gastar o mesmo tempo de uma conta real e não
  revelar quais e-mails têm conta.
- **Custo de estar errado:** com bcrypt, cada login levaria cerca de 3 s no plano gratuito. Com os
  defaults, cada hash pediria 64 MiB de 512 MB.

**2. Sessão opaca no banco, não JWT.**
- O token é `secrets.token_urlsafe(32)` e sai só no cookie.
- No banco fica só o SHA-256 em hex do token. Um vazamento do banco não entrega sessão válida.
- A validade é absoluta: `SESSAO_DIAS`, default 7, calculada pelo relógio do banco. Sessão vencida
  não autentica, e as vencidas do usuário são apagadas a cada login dele.
- Logout apaga a linha.
- **Por que não JWT:** um JWT continua válido até expirar. A sessão em banco morre com a linha:
  `ON DELETE CASCADE` de `usuarios` para `sessoes`, testado com `DELETE` em SQL cru.
- **Custo de estar errado:** com JWT, a exclusão de conta do Gate 8 deixaria sessões vivas até
  expirarem. O custo da escolha feita é uma consulta ao banco por requisição autenticada.

**3. Cookie `vs_sessao`.**
- Atributos: `HttpOnly`, `SameSite=Lax`, `Path=/`, `Max-Age` igual a `SESSAO_DIAS`, e **nunca
  `Domain`**.
- `Secure` vem de `COOKIE_SECURE`. O default é `true`; só o `.env` local o desliga.
- **Por que sem `Domain`:** `onrender.com` está na Public Suffix List, então frontend e backend no
  Render são sites diferentes, e o Safari bloqueia cookie de terceiro. O navegador vai falar só
  com o frontend, que repassa `/api/*` ao backend (fatia 3). O cookie fica first-party no domínio
  do frontend.
- **CSRF:** `SameSite=Lax`, mais corpo JSON obrigatório. O FastAPI só aceita o corpo com
  `Content-Type` JSON, e esse tipo força preflight de CORS numa requisição cross-site. Logout é
  POST.
- **Logout com o banco fora** responde 503 e limpa o cookie mesmo assim.
- **Custo de estar errado:** com `Domain` ou com o cookie no host do backend, o login quebraria em
  silêncio no Safari. Sem `Secure` em produção, a sessão poderia trafegar em HTTP.

**4. Tabelas, migração 0002** (aditiva, ADR-0011).
- `usuarios`: `email` com UNIQUE, gravado já normalizado.
- `sessoes`: `token_hash` CHAR(64) com UNIQUE; `usuario_id` com FK `ON DELETE CASCADE` e índice;
  `expira_em` com índice.
- Divergências do RFC §5.5 (errata, item 11): entra `nome_exibicao`, só para saudação na
  interface; sai `plano`.
- **Cadastro numa transação só.** `RepositorioUsuarios.criar_com_sessao` grava conta e primeira
  sessão juntas.
  - O motivo: com duas transações, um timeout na sessão deixaria a conta criada. O cenário típico
    é o Neon acordando, o mesmo do timeout abaixo. A pessoa veria 503 "tente de novo" e, ao
    tentar, receberia 409 "já existe uma conta". Para o público do produto, essa sequência é
    incompreensível.
  - O repositório continua dono da própria transação, como na fatia 1. Um teste de integração
    confere que, se a sessão não grava, a conta também não.
- **O UNIQUE decide o e-mail repetido**, sem SELECT antes. Isso cobre também a corrida entre dois
  cadastros: o `IntegrityError` daquela constraint vira 409.

**5. Validação no service, com mensagens em pt-BR** (o padrão `EntradaInvalida`).
- Nome: de 1 a 60 caracteres depois do strip.
- E-mail: strip e minúsculas antes de gravar e antes de buscar. Formato simples: um `@`, domínio
  com ponto, até 254 caracteres.
- Senha: de 8 a 128 caracteres, **sem regra de composição e sem strip**. Para quem tem baixo
  letramento digital, regra de composição empurra para senha previsível ("Senha@123").
- Os campos do corpo têm default vazio: campo ausente cai nessa validação, e não no 422 em inglês.
- **409 "Já existe uma conta com este e-mail."** revela que o e-mail tem conta. É o custo aceito
  de não haver verificação de e-mail.
- Login errado dá sempre 401 "E-mail ou senha incorretos.", com o mesmo texto para os dois casos.

**6. Timeout da autenticação: `TIMEOUT_AUTENTICACAO_S`, default 5 s** (ADR-0002).
- **Envolve só o I/O de banco** (consultas e commit). O Argon2 é CPU com custo fixo e roda numa
  thread; contá-lo no timeout transformaria disputa de CPU do plano gratuito em falso 503.
- Estourou, a resposta é 503 "O serviço está iniciando. Tente de novo em alguns segundos."
- **Separado de `TIMEOUT_PERSISTENCIA_S`** porque os dois falham de jeitos opostos:
  - a persistência descarta o registro em silêncio e a análise sai igual (troca dado por
    latência);
  - a autenticação devolve erro ao usuário (troca latência por disponibilidade).
  Uma variável só acoplaria os dois ajustes.
- **Por que 5 s:** o Neon retoma o compute em algumas centenas de milissegundos, mais o handshake
  TLS e o `pool_pre_ping` detectando conexão morta. 2 s cobre o caso típico sem margem; 5 s cobre
  com folga. O despertar do Render (até 60 s) acontece antes de a requisição chegar à aplicação e
  não entra neste orçamento.

**Logs.** Nunca registram senha, token, hash, e-mail nem id. Login recusado vira um INFO que não
identifica a conta.

## O que ficou de fora

- **Rate limit de login.** Sem Redis, o próprio custo do Argon2 limita a cerca de 4 tentativas por
  segundo por processo (estimativa: cerca de 236 ms por verificação em 0,1 CPU). Esse mesmo custo
  é um vetor de negação de serviço. Fica para a próxima fatia.
- **Exclusão de conta pela tela.** Por ora, é feita pelo contato do aviso de privacidade. O banco
  já está pronto: o CASCADE leva as sessões junto.
- **Histórico e vínculo de análise a usuário.**
- Recuperação de senha, verificação de e-mail e perfil.

## Consequências

- Cada requisição autenticada faz uma consulta a `sessoes` com join em `usuarios`. O volume do
  projeto não sente.
- Sessões vencidas de quem nunca mais volta ficam no banco até uma limpeza global, que não existe
  ainda. O índice em `expira_em` já a deixa barata quando vier.
- Uma senha de 8 caracteres sem regra de composição é mais fraca contra dicionário. O Argon2id e o
  rate limit futuro são a defesa, não a complexidade imposta ao usuário.
