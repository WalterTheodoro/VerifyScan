# ADR-0028 — Reputação de links: Google Safe Browsing e VirusTotal, só pelo domínio

**Data:** 2026-11-25 · **Status:** aceito · **Fase:** fatia 14 (RF06, RF08, objetivo da §1.5, marco M8)

## Contexto

O RFC pede duas coisas que não existiam no código: verificar URLs contra bases de phishing e
malware (RF06) e a reputação de domínios por APIs externas (RF08), com o desenho da §5.4.4. O
pacote `reputation/` tinha só uma linha de comentário, e a resposta da API trazia
`verificacao_externa_indisponivel: false` em toda análise, como se a verificação tivesse sido
feita.

Três coisas limitam o desenho. O ADR-0022 proíbe abrir o link. A regra de privacidade do projeto
proíbe mandar para fora o que a pessoa colou. E as duas APIs gratuitas têm termos de uso com
obrigações próprias, lidos na documentação oficial em 25/11/2026.

## Opções consideradas

- **Mandar a URL inteira, como a §5.4.4 descreve:** é o que as duas bases avaliam melhor, mas o
  caminho e a query de um link levam token, e-mail, CPF. Recusada pela regra de privacidade.
- **Só o Google Safe Browsing:** uma base só, sem limite apertado. Não atende ao RF08, que cita as
  duas, e deixa a verificação com um ponto único de falha.
- **As duas bases, só pelo domínio, com cache e contador no Postgres** (escolhida).

## Decisão

**O que é consultado.** Só o domínio dos primeiros três links da mensagem, sem repetir:

| Base | Chamada | O que vai |
|---|---|---|
| Google Safe Browsing | Lookup API v4, `threatMatches.find`, uma chamada para todos | `http://<host>/` e `https://<host>/` |
| VirusTotal | API v3 pública, `GET /domains/{domínio}`, uma por domínio | o domínio registrável, sem subdomínio |

Nunca vão o caminho, a query nem o fragmento. Endereço oficial de uma marca da nossa lista não é
consultado: vale o critério do DomainAnalyzer (o host é o domínio oficial ou termina em `.` + ele),
então `itau.com.br.golpe.example` é consultado. Endereço numérico vai só ao Google, porque
`/domains` não recebe IP. O sistema continua sem abrir o link.

**O VirusTotal não é só consulta.** A documentação dele diz que tudo que é consultado pela API
passa a constar na base, visível à comunidade, e pode ser examinado por ele; e pede para não
consultar indicador com dado pessoal. Consequência aceita: o domínio consultado fica público lá, e
o VirusTotal pode visitar o endereço. Não somos nós que o abrimos, mas o dono do domínio pode
perceber que alguém perguntou. Por isso vai só o domínio registrável (um subdomínio pode trazer um
nome), e o aviso de privacidade diz isso com todas as letras.

**Classificação e pesos** (`scoring/regras.yaml`, seção `reputacao`, `tipo="reputacao"`):

| Categoria | Quando | Peso |
|---|---|---|
| `reputacao_safe_browsing` | o Google devolve correspondência | +40 (RFC) |
| `reputacao_virustotal_malicioso` | `last_analysis_stats.malicious` ≥ 2 | +40 |
| `reputacao_virustotal_suspeito` | `malicious` = 1 ou `suspicious` ≥ 2 | +20 |

Os limiares do VirusTotal são escolha nossa: o RFC fala em 1–2 e 3+ detecções de uma URL, e aqui a
consulta é do domínio, que costuma ter menos detecções. Do VirusTotal sai só o fator mais forte
entre os domínios, para "malicioso" e "suspeito" não somarem 60.

**Só sobe.** O que as bases apontam vira fator do motor, somado antes da IA. `combinar()` e o
CHECK `ck_analises_nivel_e_o_maior` não mudaram. Base que não aponta nada não gera fator nem frase:
silêncio não é atestado de segurança.

**Falha nunca derruba a análise (RNF09).** As duas bases em paralelo, cada uma no teto de 3 s
(`REPUTACAO_TIMEOUT_S`, só pode baixar). Erro, timeout, 429, resposta fora do esperado, chave
ausente ou cota esgotada: aquela base fica de fora e a resposta leva
`verificacao_externa_indisponivel: true`. A flag só é verdadeira quando havia domínio para
consultar; mensagem sem link sai `false`.

**Limite do VirusTotal.** A API pública permite 4 consultas por minuto e 500 por dia. A tabela
`reputacao_uso` conta as consultas de todo mundo por minuto e por dia; a reserva é feita antes da
chamada, nos dois limites, numa transação. Sem reserva (limite atingido, ou banco fora), o
VirusTotal não é chamado. Os limites estão no `Settings` com o teto dos termos: só dá para baixar.
A documentação não diz quando o limite diário zera; o contador usa o dia de UTC, como suposição.

**Cache no Postgres** (`reputacao_cache`, migração 0008), e não no Redis da §5.4.4: o Redis está
desligado em produção. A chave é o SHA-256 do host ou do domínio; o domínio em claro não é
gravado, e a linha não tem pessoa, análise nem hora do pedido.

- VirusTotal: 24 horas, qualquer veredito.
- Safe Browsing: só a correspondência, e só pelo `cacheDuration` que o Google devolve. Nesse prazo
  o host continua apontado e não é perguntado de novo, como os termos exigem. Resposta sem
  correspondência não é guardada: a documentação da Lookup API não define prazo para ela.

A tabela se limpa ao gravar: cada gravação apaga o que venceu.

**Termos do Google na tela.** As frases dizem "possivelmente", nunca "com certeza". No fator e no
link que vieram do Google aparece "Aviso fornecido pelo Google", como link para a página de aviso
indicada nos termos (nova aba, `rel="noopener noreferrer"`), e "A informação pode não ser precisa."
Nada disso aparece no que veio do VirusTotal. É o único link de saída da placa do resultado, e é
fixo: não vem da mensagem.

**Histórico.** O fator é gravado com a análise (invariante 6). No histórico ele aparece como uma
linha só, neutra: "Na data desta análise, uma base de reputação externa apontava este domínio como
possivelmente perigoso." Sem a base, sem atribuição e sem afirmar o estado de hoje.

**As chaves.** `SAFE_BROWSING_API_KEY` e `VIRUSTOTAL_API_KEY`, opcionais, `SecretStr`. A do
VirusTotal vai no cabeçalho `x-apikey`. A do Google vai na query (`?key=`), a única forma
documentada, e por isso há três travas: nenhuma exceção nossa carrega a URL (`FonteIndisponivel`
leva só o motivo, com `from None`); o log do cliente HTTP (`httpx`, `httpcore`), que escreve a URL
de cada chamada, fica desligado; e a limpeza do evento do Sentry corta no `?` o nome do trecho de
uma chamada HTTP. Há teste para cada uma.

**Observabilidade.** `verifyscan_reputacao_consultas_total{fonte, resultado}` e
`verifyscan_reputacao_falhas_total{fonte, motivo}`, e o evento `reputacao_indisponivel`. O domínio
nunca é rótulo nem campo.

**Avaliação do corpus.** O `avaliar_corpus` roda sem reputação: ele usa o `ServicoAnalise`, que é
puro, e quem consulta as bases é o orquestrador. Os números continuam reproduzíveis e não dependem
de rede nem do que as bases dizem no dia.

## Consequências

- **Tempo (invariante 8, RNF01).** A reputação roda ao mesmo tempo que a janela da cota, antes da
  IA. A etapa que era de 1,5 s passa a ser de até 3 s. Pior caso: texto de ≈ 18,8 s para ≈ 20,3 s;
  print de ≈ 24 s para ≈ 27 s.
- **Consultar só o domínio perde precisão.** Uma página maliciosa dentro de um domínio comum
  (um site de arquivos, um blog) não é apontada pelo domínio. Encurtadores são o caso extremo:
  consultar `bit.ly` não diz nada sobre o link curto. O sinal léxico de encurtador continua valendo.
- **Zona cinzenta dos termos do Google no histórico.** Os termos só permitem mostrar o aviso
  enquanto a resposta em cache é válida. O histórico mostra, dias depois, um registro do que a
  nossa análise viu. A frase neutra, sem atribuição e sem falar do presente, é a nossa leitura de
  boa-fé; não é uma permissão escrita nos termos.
- **Uso não comercial.** As duas APIs gratuitas são só para uso não comercial. Serve a um TCC; um
  produto pago precisaria do Web Risk do Google e da API paga do VirusTotal.
- **O limite do VirusTotal é de todo mundo junto.** Com 500 consultas por dia e até 3 por análise,
  um dia movimentado esgota a cota, e daí em diante as análises saem com a flag de indisponível.
- **Formato da resposta do VirusTotal.** O caminho `data.attributes.last_analysis_stats`, o 404
  para domínio desconhecido e o 429 para cota vêm do que se conhece da API; a página de referência
  lida não os descreve. Qualquer resposta fora do esperado vira "indisponível", nunca erro.
- **`httpx` passou a ser dependência de execução** (0.28.1, de 06/12/2024). Já estava no lock,
  pelo grupo de desenvolvimento; o SDK da Anthropic não o traz (usa o `httpx2`).
- **A flag `verificacao_externa_indisponivel` deixou de ser sempre `false`.** Em ambiente sem as
  chaves, toda análise com link sai com ela `true`. É a verdade.
- **Não verificado:** nenhuma chamada real às duas APIs foi feita (não há chave no ambiente de
  desenvolvimento, e teste não usa rede). Os testes de integração do cache e do contador rodam só
  no CI. A primeira chamada de verdade acontece quando as chaves forem cadastradas no Render.
