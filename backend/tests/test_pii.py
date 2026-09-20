"""Detectores de PII (`tools/pii.py`) — o que precisa ser encontrado antes de virar commit.

Todos os CPFs aqui são sintéticos: bases óbvias ("123456789", "111444777") com os dígitos
verificadores calculados à mão para o teste. Nenhum pertence a pessoa alguma.
"""

import pytest

from tools.pii import (
    Achado,
    detectar_cpf,
    detectar_email,
    detectar_telefone,
    detectar_valor_monetario,
    varrer,
)


def valores(achados: list[Achado]) -> list[str]:
    return [achado.valor for achado in achados]


# ─── CPF ──────────────────────────────────────────────────────────────────────────────────


def test_cpf_pontuado_e_detectado() -> None:
    (achado,) = detectar_cpf("Confirme o CPF 123.456.789-09 para liberar")

    assert achado.tipo == "cpf"
    assert achado.valor == "123.456.789-09"
    assert achado.inicio == 15
    assert achado.fim == 29


def test_cpf_sem_pontuacao_e_detectado() -> None:
    assert valores(detectar_cpf("Informe 11144477735 no atendimento")) == ["11144477735"]


def test_cpf_com_digito_verificador_errado_e_ignorado() -> None:
    """O último dígito correto é 9; com 0 o número não é um CPF e não deve virar achado."""
    assert detectar_cpf("Confirme o CPF 123.456.789-00 para liberar") == []


@pytest.mark.parametrize(
    "texto",
    [
        pytest.param("111.111.111-11", id="pontuado"),
        pytest.param("11111111111", id="sem-pontuacao"),
        pytest.param("00000000000", id="zeros"),
    ],
)
def test_cpf_de_digitos_repetidos_e_ignorado(texto: str) -> None:
    """Passam no módulo 11 por acidente aritmético, mas são preenchimento, não CPF."""
    assert detectar_cpf(texto) == []


def test_sequencia_maior_que_onze_digitos_nao_e_cpf() -> None:
    """Sem os lookarounds, um código de 14 dígitos doaria 11 dígitos para o padrão."""
    assert detectar_cpf("Pedido 12345678909123 confirmado") == []


def test_varios_cpfs_na_ordem_em_que_aparecem() -> None:
    texto = "Titular 123.456.789-09, dependente 11144477735"

    assert valores(detectar_cpf(texto)) == ["123.456.789-09", "11144477735"]


# ─── telefone ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "telefone",
    [
        pytest.param("(11) 98765-4321", id="celular-parenteses-e-hifen"),
        pytest.param("(11)98765-4321", id="celular-parenteses-sem-espaco"),
        pytest.param("11 98765-4321", id="celular-ddd-sem-parenteses"),
        pytest.param("11987654321", id="celular-so-digitos"),
        pytest.param("98765-4321", id="celular-sem-ddd"),
        pytest.param("+55 11 98765-4321", id="celular-com-prefixo-do-pais"),
        pytest.param("+5511987654321", id="celular-com-prefixo-tudo-junto"),
        pytest.param("(47) 3344-5566", id="fixo-parenteses-e-hifen"),
        pytest.param("47 3344-5566", id="fixo-ddd-sem-parenteses"),
        pytest.param("3344-5566", id="fixo-sem-ddd"),
        pytest.param("33445566", id="fixo-so-digitos"),
    ],
)
def test_formatos_de_telefone(telefone: str) -> None:
    (achado,) = detectar_telefone(f"Me chama no {telefone} hoje")

    assert achado.tipo == "telefone"
    assert achado.valor == telefone


def test_telefone_nao_casa_com_data_nem_com_valor() -> None:
    assert detectar_telefone("Vence em 05/09/2025 no valor de R$ 1.234,56") == []


# ─── e-mail ───────────────────────────────────────────────────────────────────────────────


def test_email_e_detectado() -> None:
    (achado,) = detectar_email("Escreva para contato@banco.com.br hoje")

    assert achado.tipo == "email"
    assert achado.valor == "contato@banco.com.br"


def test_ponto_final_da_frase_nao_entra_no_email() -> None:
    assert valores(detectar_email("Responda a joao.silva+cobranca@exemplo.com.")) == [
        "joao.silva+cobranca@exemplo.com"
    ]


def test_texto_sem_arroba_nao_tem_email() -> None:
    assert detectar_email("Acesse www.banco.com.br para atualizar") == []


# ─── valor monetário ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "valor",
    [
        pytest.param("R$ 1.234,56", id="milhar-e-centavo"),
        pytest.param("R$ 50", id="inteiro-sem-centavo"),
        pytest.param("R$50,00", id="sem-espaco-depois-do-cifrao"),
        pytest.param("R$ 1.500.000,00", id="milhao"),
        pytest.param("1.234,56 reais", id="palavra-reais"),
        pytest.param("50 reais", id="inteiro-com-palavra-reais"),
    ],
)
def test_formatos_de_valor_monetario(valor: str) -> None:
    (achado,) = detectar_valor_monetario(f"Transfira {valor} agora")

    assert achado.tipo == "valor_monetario"
    assert achado.valor == valor


def test_numero_solto_nao_e_valor_monetario() -> None:
    """Sem "R$" e sem "reais" não há evidência de quantia — seria falso positivo em série."""
    assert detectar_valor_monetario("O protocolo 1.234 foi aberto") == []


# ─── varredura ────────────────────────────────────────────────────────────────────────────


def test_varrer_junta_os_quatro_na_ordem_do_texto() -> None:
    texto = (
        "Oi, sou do banco. Pague R$ 250,00 usando o CPF 123.456.789-09, "
        "responda em fraude@banco-seguro.xyz ou ligue (11) 98765-4321."
    )

    achados = varrer(texto)

    assert [(achado.tipo, achado.valor) for achado in achados] == [
        ("valor_monetario", "R$ 250,00"),
        ("cpf", "123.456.789-09"),
        ("email", "fraude@banco-seguro.xyz"),
        ("telefone", "(11) 98765-4321"),
    ]
    # O guard vai usar o par (inicio, fim) para apontar o trecho no arquivo: ele precisa
    # recortar exatamente o valor reportado.
    assert all(texto[achado.inicio : achado.fim] == achado.valor for achado in achados)


def test_texto_limpo_nao_gera_achado() -> None:
    texto = "Voce ganhou um premio! Clique no link e resgate agora antes que expire."

    assert varrer(texto) == []


def test_texto_vazio_nao_quebra() -> None:
    assert varrer("") == []
