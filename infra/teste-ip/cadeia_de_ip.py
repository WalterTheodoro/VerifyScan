"""Teste da cadeia de IP da cota, de ponta a ponta (ADR-0029).

Roda DENTRO de um contêiner cliente, na rede do compose, contra a pilha de verdade: Caddy →
frontend (proxy.ts) → backend → Postgres. O que ele prova:

1. `forjar`: um `X-Forwarded-For` (ou qualquer outro cabeçalho de IP) forjado pelo visitante NÃO
   muda a chave da cota. O observável é o limite de contas novas por IP no dia (ADR-0024): com um
   IP forjado diferente a cada pedido, o cadastro que passa do limite tem de ser recusado mesmo
   assim. Se o forjado valesse, cada pedido teria uma chave nova e nenhum seria recusado.
2. `outro-ip`: o IP real chega ao backend. Um segundo cliente, com outro IP, ainda consegue se
   cadastrar depois de o primeiro esgotar o limite. Se todo mundo caísse numa chave só (o IP do
   Caddy ou do frontend), este cadastro seria recusado.

3. `provocar-erro`: a parte do log (invariante 2). Com o frontend parado, faz um pedido que o
   Caddy responde com 502, levando marcas na query, no cookie e num IP forjado. Quem confere é
   o CI, de fora: o log do Caddy tem de ter a linha do 502 e não pode ter o IP deste cliente,
   nem nenhuma das marcas.

A ordem importa: `forjar` no primeiro cliente, depois `outro-ip` no segundo; `provocar-erro` por
último, porque para o frontend. Só biblioteca padrão.

    python cadeia_de_ip.py forjar
    python cadeia_de_ip.py outro-ip
    python cadeia_de_ip.py provocar-erro
"""

import json
import os
import secrets
import sys
import urllib.error
import urllib.request

# O Caddy, pelo nome do serviço no compose. Trocar o alvo serve para ver o teste falhar: direto
# no frontend (http://frontend:3000) ninguém sobrescreve o X-Forwarded-For.
ALVO = os.environ.get("ALVO", "http://caddy")
# O default de CADASTROS_POR_IP_POR_DIA, que o compose de teste não muda.
LIMITE_DE_CADASTROS = 5
CRIADO = 201
RECUSADO_PELO_LIMITE = 429
SEM_FRONTEND = 502
# O que o CI procura no log do Caddy depois do `provocar-erro`. Nenhuma das duas pode aparecer.
MARCA_NO_PEDIDO = "MARCA-DO-TESTE-DE-LOG"
IP_FORJADO_NO_ERRO = "198.51.100.200"


def cabecalhos_forjados(n: int) -> dict[str, str]:
    """Tudo o que um visitante poderia mandar para se passar por outro IP, diferente a cada `n`."""
    return {
        "X-Forwarded-For": f"198.51.100.{n}, 203.0.113.{n}",
        "X-Real-IP": f"198.51.100.{n}",
        "Forwarded": f"for=198.51.100.{n}",
        # Os dois cabeçalhos do nosso proxy: sem o segredo certo, o backend ignora.
        "X-VerifyScan-IP": f"198.51.100.{n}",
        "X-VerifyScan-Segredo": "chute-do-visitante",
    }


def cadastrar(cabecalhos: dict[str, str]) -> int:
    """Cria uma conta nova e devolve o status. E-mail aleatório: nunca esbarra no 409."""
    corpo = json.dumps(
        {
            "nome": "Teste da cadeia de IP",
            "email": f"cadeia-{secrets.token_hex(8)}@exemplo.invalid",
            "senha": "senha-so-do-teste",
        }
    ).encode()
    pedido = urllib.request.Request(
        f"{ALVO}/api/auth/cadastro",
        data=corpo,
        headers={"Content-Type": "application/json", **cabecalhos},
        method="POST",
    )
    try:
        with urllib.request.urlopen(pedido, timeout=30) as resposta:
            return int(resposta.status)
    except urllib.error.HTTPError as erro:
        return erro.code


def conferir(descricao: str, recebido: int, esperado: int) -> None:
    if recebido != esperado:
        print(f"FALHOU: {descricao}: esperava {esperado}, veio {recebido}.")
        sys.exit(1)
    print(f"ok: {descricao} ({recebido})")


def forjar() -> None:
    for n in range(1, LIMITE_DE_CADASTROS + 1):
        conferir(
            f"cadastro {n} de {LIMITE_DE_CADASTROS}, com IP forjado",
            cadastrar(cabecalhos_forjados(n)),
            CRIADO,
        )
    conferir(
        "cadastro além do limite, com outro IP forjado, é recusado",
        cadastrar(cabecalhos_forjados(LIMITE_DE_CADASTROS + 1)),
        RECUSADO_PELO_LIMITE,
    )


def outro_ip() -> None:
    conferir("cadastro de um segundo cliente, com outro IP real", cadastrar({}), CRIADO)


def provocar_erro() -> None:
    pedido = urllib.request.Request(
        f"{ALVO}/api/auth/eu?q={MARCA_NO_PEDIDO}",
        headers={
            "Cookie": f"vs_sessao={MARCA_NO_PEDIDO}",
            "X-Forwarded-For": IP_FORJADO_NO_ERRO,
        },
    )
    try:
        with urllib.request.urlopen(pedido, timeout=30) as resposta:
            recebido = int(resposta.status)
    except urllib.error.HTTPError as erro:
        recebido = erro.code
    conferir("pedido com o frontend parado é respondido pelo Caddy", recebido, SEM_FRONTEND)


PARTES = {"forjar": forjar, "outro-ip": outro_ip, "provocar-erro": provocar_erro}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in PARTES:
        print(f"uso: python cadeia_de_ip.py {' | '.join(PARTES)}")
        sys.exit(2)
    PARTES[sys.argv[1]]()
