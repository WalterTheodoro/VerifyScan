"""O filtro do log do Caddy (`infra/Caddyfile`), conferido no texto do arquivo.

O efeito de verdade é conferido com o Caddy rodando: o campo `request`, pelo job da cadeia de IP
do CI (`infra/teste-ip/`); o campo `remote`, provocando a emissão de um certificado (diário de
27/11/2026). Este teste só impede que uma das duas linhas saia do arquivo sem ninguém notar.
"""

import re
from pathlib import Path

CADDYFILE = Path(__file__).resolve().parents[2] / "Caddyfile"


def _campos_apagados() -> set[str]:
    """Os campos que o bloco `fields` do filtro do log manda apagar."""
    sem_comentarios = "\n".join(
        linha for linha in CADDYFILE.read_text(encoding="utf-8").splitlines() if "#" not in linha
    )
    bloco = re.search(r"format filter \{.*?fields \{(.*?)\}", sem_comentarios, flags=re.DOTALL)
    assert bloco is not None, "o Caddyfile não tem mais o filtro do log"
    apagados = set()
    for linha in bloco.group(1).splitlines():
        partes = linha.split()
        if len(partes) == 2 and partes[1] == "delete":
            apagados.add(partes[0])
    return apagados


def test_o_log_nao_leva_o_pedido_nem_o_endereco_de_quem_conectou() -> None:
    # `request`: IP do visitante, URL com a query e cabeçalhos, na linha de erro do repasse.
    # `remote`: IP e porta de quem conectou, nas linhas da validação do certificado.
    assert _campos_apagados() >= {"request", "remote"}
