"""IP de quem pediu, atrás do proxy do Next (ADR-0014, ADR-0024).

O frontend repassa o IP do visitante em `X-VerifyScan-IP`, junto com o segredo compartilhado. Sem
o segredo certo o cabeçalho é ignorado: o backend também é acessível direto, e qualquer um poderia
mandá-lo. Fora do proxy, vale a entrada mais à direita do `X-Forwarded-For` — a que o Render
acrescentou, e que o cliente não forja.
"""

import pytest
from starlette.datastructures import Headers

from app.core.ip import IP_DESCONHECIDO, chave_hmac, ip_do_visitante, normalizar_ip

SEGREDO = "segredo-do-proxy-com-mais-de-32-caracteres"


def _cabecalhos(*pares: tuple[str, str]) -> Headers:
    return Headers(raw=[(nome.encode(), valor.encode()) for nome, valor in pares])


def test_com_o_segredo_certo_vale_o_ip_repassado() -> None:
    cabecalhos = _cabecalhos(
        ("x-verifyscan-segredo", SEGREDO),
        ("x-verifyscan-ip", "198.51.100.7"),
        ("x-forwarded-for", "203.0.113.1, 10.0.0.9"),
    )

    assert ip_do_visitante(cabecalhos, "10.0.0.2", SEGREDO) == "198.51.100.7"


@pytest.mark.parametrize(
    "segredo_recebido",
    [None, "", "segredo-errado-com-mais-de-32-caracteres!", SEGREDO[:-1], SEGREDO + "x"],
)
def test_sem_o_segredo_certo_o_ip_repassado_e_ignorado(segredo_recebido: str | None) -> None:
    pares = [("x-verifyscan-ip", "198.51.100.7"), ("x-forwarded-for", "203.0.113.1")]
    if segredo_recebido is not None:
        pares.append(("x-verifyscan-segredo", segredo_recebido))

    assert ip_do_visitante(_cabecalhos(*pares), "10.0.0.2", SEGREDO) == "203.0.113.1"


def test_segredo_certo_com_ip_invalido_cai_no_x_forwarded_for() -> None:
    cabecalhos = _cabecalhos(
        ("x-verifyscan-segredo", SEGREDO),
        ("x-verifyscan-ip", "não é ip"),
        ("x-forwarded-for", "203.0.113.1"),
    )

    assert ip_do_visitante(cabecalhos, "10.0.0.2", SEGREDO) == "203.0.113.1"


def test_vale_a_entrada_mais_a_direita_do_x_forwarded_for() -> None:
    """A da esquerda pode ter vindo do cliente: o Render acrescenta, não substitui."""
    cabecalhos = _cabecalhos(("x-forwarded-for", "1.2.3.4, 203.0.113.9"))

    assert ip_do_visitante(cabecalhos, "10.0.0.2", SEGREDO) == "203.0.113.9"


def test_x_forwarded_for_repetido_vale_a_ultima_linha() -> None:
    """Dois cabeçalhos com o mesmo nome: o primeiro pode ter vindo do cliente."""
    cabecalhos = _cabecalhos(("x-forwarded-for", "1.2.3.4"), ("x-forwarded-for", "203.0.113.9"))

    assert ip_do_visitante(cabecalhos, "10.0.0.2", SEGREDO) == "203.0.113.9"


def test_entrada_mais_a_direita_invalida_nao_volta_para_a_esquerda() -> None:
    cabecalhos = _cabecalhos(("x-forwarded-for", "1.2.3.4, lixo"))

    assert ip_do_visitante(cabecalhos, "10.0.0.2", SEGREDO) == "10.0.0.2"


def test_sem_cabecalho_vale_o_ip_da_conexao() -> None:
    assert ip_do_visitante(_cabecalhos(), "10.0.0.2", SEGREDO) == "10.0.0.2"


def test_sem_nada_valido_e_desconhecido() -> None:
    assert ip_do_visitante(_cabecalhos(), None, SEGREDO) == IP_DESCONHECIDO


def test_ipv6_e_agrupado_por_64() -> None:
    """Quem tem um /64 troca de endereço à vontade; o limite é por rede, não por endereço."""
    assert normalizar_ip("2001:db8:1:2:aaaa::1") == normalizar_ip("2001:db8:1:2:bbbb::9")
    assert normalizar_ip("2001:db8:1:2::1") != normalizar_ip("2001:db8:1:3::1")


def test_ipv4_mapeado_em_ipv6_vira_ipv4() -> None:
    assert normalizar_ip("::ffff:203.0.113.9") == "203.0.113.9"


def test_espacos_em_volta_sao_ignorados() -> None:
    assert normalizar_ip(" 203.0.113.9 ") == "203.0.113.9"


@pytest.mark.parametrize("texto", ["", "lixo", "300.1.1.1", "203.0.113.9:443"])
def test_texto_que_nao_e_ip_e_recusado(texto: str) -> None:
    assert normalizar_ip(texto) is None


def test_chave_hmac_nao_contem_o_ip_e_depende_do_segredo() -> None:
    chave = chave_hmac("um-segredo", "203.0.113.9")

    assert "203.0.113.9" not in chave
    assert len(chave) == 64
    assert chave == chave_hmac("um-segredo", "203.0.113.9")
    assert chave != chave_hmac("outro-segredo", "203.0.113.9")
