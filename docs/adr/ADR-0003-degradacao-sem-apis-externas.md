# ADR-0003 — Degradação sem APIs externas e reinterpretação do RNF02

**Data:** 2026-08-27 · **Status:** aceito · **Fases:** 4, 7, 9

## Contexto

O produto depende de três serviços que não controlamos: VirusTotal, Google Safe Browsing e a API
da LLM. O RFC trata as três como enriquecimento (§3.2), e a indisponibilidade da LLM já é requisito
(RNF08) e risco (R-04). A indisponibilidade das APIs de reputação é só fluxo alternativo e risco
R-01 — lacuna registrada no achado 4 e encaminhada à errata como RNF09.

Além disso, a **API pública do VirusTotal é limitada a 4 requisições por minuto e 500 por dia, e
seus termos vedam uso em produto comercial** (reconferir na documentação no início da Fase 4).
Isso colide de frente com o RNF02 — "no mínimo 100 usuários simultâneos sem degradação": nenhuma
arquitetura entrega 100 simultâneos passando cada análise pela VT.

## Opções consideradas

1. **Rebaixar o RNF02** para um número que a cota permita. Honesto, mas joga fora um requisito que
   não está errado — e some com a medição do que o sistema realmente aguenta.
2. **Ignorar a colisão** e medir com a VT ligada. Mede a cota da VT, não o sistema.
3. **Reinterpretar o RNF02 por escrito**, dizendo qual caminho ele mede, e publicar as duas
   medições.

## Decisão

**Degradação.** Toda chamada externa tem timeout curto (ADR-0002), falha em silêncio e marca a
resposta: `verificacao_externa_indisponivel: true` para reputação, `explicacao_indisponivel: true`
para a LLM. A análise nunca falha por causa de um terceiro. Só consulta de relatório existente na
VT — nunca submeter URL e aguardar análise, que queima cota e estoura o orçamento de 30 s. Cache
Redis com TTL de 24 h e rate limiter local respeitando o limite por minuto, com *fail fast*.

**RNF02 passa a ler:** *"o sistema deve suportar no mínimo 100 usuários simultâneos no caminho que
não depende de cota de API externa."*

Medição na Fase 9 em duas execuções, ambas para a monografia, lado a lado:

1. provedores de reputação **mockados** — mede a arquitetura;
2. provedores **reais ligados** — mede o que o usuário final obteria hoje, com a cota gratuita.

## Consequências

- O requisito não foi rebaixado: foi **especificado**. Ele estava subespecificado quanto a qual
  caminho media, e é isso que a banca vai ouvir.
- A limitação da cota vira conteúdo do capítulo de limitações, com número medido em vez de
  suposição.
- O RFC precisa da errata (RNF09) para que "operar sem reputação externa" tenha status de
  requisito, e não de nota de rodapé.
- Custo de errar, registrado: sem a reinterpretação, o teste de carga da Fase 9 mede a cota da
  VirusTotal e reprova o sistema por um limite que não é dele.
