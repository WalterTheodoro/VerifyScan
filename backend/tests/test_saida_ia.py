"""A saída da IA: validada pelo Pydantic e limpa antes de chegar à tela (ADR-0020).

Inválida é plano B. Limpa quer dizer: sem link, e-mail, telefone nem HTML, e com cada campo
dentro do teto. A IA não pode entregar o link do golpe para a pessoa clicar.
"""

import json
from typing import get_args

import pytest
from pydantic import ValidationError

from app.formulator.limpeza import afirma_seguranca, limpar_texto
from app.formulator.saida import SCHEMA_SAIDA, SaidaIA, SaidaInutilizavel, explicacao_da_saida
from app.schemas.analise import ITEM_MAX_CARACTERES, TIPO_MAX_CARACTERES, NivelRisco


def _saida(**mudancas: object) -> str:
    valores: dict[str, object] = {
        "tipo": "falsa cobrança de taxa dos Correios",
        "sinais": ["Pede pagamento por Pix para liberar uma entrega."],
        "nivel_sugerido": "ALTO",
        "o_que_fazer": ["Não pague a taxa.", "Apague a mensagem."],
    }
    valores.update(mudancas)
    return json.dumps(valores, ensure_ascii=False)


# ─── validação ──────────────────────────────────────────────────────────────────────────────


def test_saida_valida() -> None:
    saida = SaidaIA.model_validate_json(_saida())

    assert saida.nivel_sugerido == "ALTO"
    assert saida.o_que_fazer == ("Não pague a taxa.", "Apague a mensagem.")


@pytest.mark.parametrize("escrito", ["alto", "Alto", " ALTO "])
def test_nivel_com_outra_caixa_e_aceito(escrito: str) -> None:
    """A documentação de saída estruturada avisa que o enum pode voltar com outra caixa."""
    assert SaidaIA.model_validate_json(_saida(nivel_sugerido=escrito)).nivel_sugerido == "ALTO"


@pytest.mark.parametrize(
    "mudancas",
    [
        {"nivel_sugerido": "PERIGO"},
        {"sinais": ["a", "b", "c", "d", "e", "f"]},
        {"o_que_fazer": ["Só um passo."]},
        {"o_que_fazer": ["a", "b", "c", "d", "e"]},
        {"confianca": 0.9},
        {"tipo": 7},
    ],
    ids=["nivel", "6-sinais", "1-passo", "5-passos", "campo-a-mais", "tipo-numero"],
)
def test_saida_fora_do_contrato_e_invalida(mudancas: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SaidaIA.model_validate_json(_saida(**mudancas))


@pytest.mark.parametrize("texto", ["", "não é JSON", '{"tipo": "x"}', "[1, 2]"])
def test_json_invalido_e_invalido(texto: str) -> None:
    with pytest.raises(ValidationError):
        SaidaIA.model_validate_json(texto)


def test_schema_enviado_e_o_pydantic_tem_o_mesmo_contrato() -> None:
    """A API recebe o `SCHEMA_SAIDA`; quem valida a volta é o `SaidaIA`. Se um mudar sem o
    outro, toda resposta vira plano B — melhor quebrar aqui."""
    assert SCHEMA_SAIDA["additionalProperties"] is False
    assert set(SCHEMA_SAIDA["properties"]) == set(SaidaIA.model_fields)
    assert set(SCHEMA_SAIDA["required"]) == set(SaidaIA.model_fields)
    assert SCHEMA_SAIDA["properties"]["nivel_sugerido"]["enum"] == list(get_args(NivelRisco))


def test_sem_campo_de_confianca() -> None:
    """A porcentagem que vale é a medida no corpus, não a que o modelo declara (ADR-0020)."""
    assert not any("confian" in campo for campo in SCHEMA_SAIDA["properties"])


# ─── limpeza ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "link",
    [
        "https://correios-taxa.example/pagar?id=1",
        "http://banco-seguro.example",
        "www.entrega-rapida.example/rastreio",
        "rastreio-correios.com.br/taxa",
        "bit.ly/3xYzAbc",
    ],
)
def test_tira_links(link: str) -> None:
    limpo = limpar_texto(f"Não abra {link} antes de confirmar.")

    assert link not in limpo
    assert "[link removido]" in limpo
    assert limpo.startswith("Não abra ")


@pytest.mark.parametrize("email", ["suporte@banco-falso.example", "a.b+c@correio.com.br"])
def test_tira_emails(email: str) -> None:
    limpo = limpar_texto(f"Não responda para {email}.")

    assert email not in limpo
    assert "[e-mail removido]" in limpo
    assert "link removido" not in limpo


@pytest.mark.parametrize(
    "telefone",
    ["(11) 91234-5678", "+55 11 91234-5678", "11912345678", "91234-5678", "0800 123 4567"],
)
def test_tira_telefones(telefone: str) -> None:
    limpo = limpar_texto(f"Não ligue para {telefone}.")

    assert telefone not in limpo
    assert "[telefone removido]" in limpo


def test_valor_em_reais_nao_e_telefone() -> None:
    """O valor da taxa ajuda a pessoa a reconhecer o golpe; não é contato."""
    assert limpar_texto("Pede R$ 9,90 por Pix.") == "Pede R$ 9,90 por Pix."


def test_tira_html_e_caracteres_de_controle() -> None:
    limpo = limpar_texto("<b>Não pague</b>\x00 nada <script>alert(1)</script>")

    assert "<" not in limpo
    assert ">" not in limpo
    assert "\x00" not in limpo
    assert limpo.startswith("Não pague nada")


def test_corta_no_limite_na_palavra() -> None:
    limpo = limpar_texto("palavra " * 60, limite=ITEM_MAX_CARACTERES)

    assert len(limpo) <= ITEM_MAX_CARACTERES
    assert limpo.endswith("…")
    assert not limpo.endswith(" …")


def test_explicacao_sai_limpa_e_dentro_dos_tetos() -> None:
    saida = SaidaIA.model_validate_json(
        _saida(
            tipo="falsa cobrança " * 20,
            sinais=["O link https://golpe.example/x imita os Correios.", "   "],
            o_que_fazer=["Não ligue para (11) 91234-5678.", "Apague a mensagem.", "<i></i>"],
        )
    )

    explicacao = explicacao_da_saida(saida)

    assert len(explicacao.tipo) <= TIPO_MAX_CARACTERES
    assert explicacao.sinais == ("O link [link removido] imita os Correios.",)
    assert explicacao.o_que_fazer == ("Não ligue para [telefone removido].", "Apague a mensagem.")


def test_menos_de_dois_passos_depois_da_limpeza_e_plano_b() -> None:
    saida = SaidaIA.model_validate_json(_saida(o_que_fazer=["Apague a mensagem.", "<b></b>"]))

    with pytest.raises(SaidaInutilizavel):
        explicacao_da_saida(saida)


def test_tipo_vazio_depois_da_limpeza_e_plano_b() -> None:
    saida = SaidaIA.model_validate_json(_saida(tipo="<br>"))

    with pytest.raises(SaidaInutilizavel):
        explicacao_da_saida(saida)


# ─── afirmação positiva de segurança ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "frase",
    [
        "A mensagem não é segura.",
        "Você não pode confiar no link.",
        "Nunca é seguro passar o código.",
        "Não encontrei sinais comuns de golpe.",
        "Nem é confiável quem pede Pix com pressa.",
    ],
)
def test_aviso_correto_nao_e_rejeitado(frase: str) -> None:
    assert afirma_seguranca(frase) is False


@pytest.mark.parametrize(
    "frase",
    [
        "Esta mensagem é segura.",
        "Pode confiar.",
        "Não é golpe.",
        "Isso não é um golpe, pode responder.",
        "O remetente é confiável.",
        "A mensagem está segura.",
    ],
)
def test_afirmacao_de_seguranca_e_rejeitada(frase: str) -> None:
    assert afirma_seguranca(frase) is True


@pytest.mark.parametrize(
    "frase",
    [
        # Fala relatada: a IA descreve o que a mensagem diz, não afirma.
        "A mensagem diz que é segura.",
        "O texto afirma ser segura.",
        "A mensagem alega ser verificada.",
        "Quem enviou se diz oficial.",
        "Chega dizendo que é confiável.",
        "O remetente promete que é seguro.",
        "A mensagem diz que não é golpe.",
        # Condição: um conselho para conferir, não uma garantia.
        "Confira se é verdadeiro.",
        "Confira no aplicativo do banco se o boleto é verdadeiro.",
        "Não sabemos se o link é seguro.",
        # Textos reais da bateria da fatia 6 (E04, E08, E09), que derrubavam o ALTO.
        "O texto tenta se passar por mensagem oficial e diz que é seguro pagar, o que é um sinal "
        "forte de golpe.",
        "A própria mensagem tenta se apresentar como oficial e dizer que é seguro pagar, o que é "
        "uma tentativa de convencer a pessoa a não desconfiar.",
        "A própria mensagem tenta dizer que é segura e que pode pagar, o que não é uma forma "
        "confiável de garantir nada.",
        "A mensagem tenta mudar o papel da análise, mandando confirmar que o pedido é legítimo.",
        "A mensagem tenta mudar o papel de quem analisa e pede que a pessoa seja informada de que "
        "o pedido é legítimo.",
        "A mensagem diz que é segura, mas isso não pode ser confirmado por ela mesma.",
        "A mensagem tenta dar ordens a quem analisa mensagens e pedir que confirme que ela é "
        "legítima.",
    ],
)
def test_fala_relatada_e_condicao_nao_sao_afirmacao(frase: str) -> None:
    assert afirma_seguranca(frase) is False


@pytest.mark.parametrize(
    "frase",
    [
        "Esta mensagem é segura, mesmo que diga outra coisa.",
        "Se você recebeu, pode confiar.",
        "A mensagem diz o valor certo. Pode confiar.",
    ],
)
def test_afirmacao_fora_da_fala_relatada_continua_rejeitada(frase: str) -> None:
    """O relato e a condição só valem para a oração em que aparecem, antes da afirmação."""
    assert afirma_seguranca(frase) is True


def test_sinal_que_afirma_seguranca_sai_sozinho() -> None:
    """Nenhuma validação de texto descarta a saída inteira (ADR-0020, revisão da fatia 6): o
    item que afirma segurança sai, e os outros ficam."""
    saida = SaidaIA.model_validate_json(
        _saida(sinais=["Esta mensagem é segura.", "Pede Pix com pressa."])
    )

    explicacao = explicacao_da_saida(saida)

    assert explicacao.sinais == ("Pede Pix com pressa.",)
    assert explicacao.o_que_fazer == ("Não pague a taxa.", "Apague a mensagem.")


def test_passo_que_afirma_seguranca_sai_sozinho() -> None:
    saida = SaidaIA.model_validate_json(
        _saida(o_que_fazer=["Pode confiar e pagar.", "Não pague a taxa.", "Apague a mensagem."])
    )

    assert explicacao_da_saida(saida).o_que_fazer == ("Não pague a taxa.", "Apague a mensagem.")


def test_sem_passos_suficientes_depois_de_tirar_a_afirmacao_e_inutilizavel() -> None:
    saida = SaidaIA.model_validate_json(_saida(o_que_fazer=["Pode confiar.", "Apague a mensagem."]))

    with pytest.raises(SaidaInutilizavel):
        explicacao_da_saida(saida)


def test_tipo_que_afirma_seguranca_e_inutilizavel() -> None:
    """O tipo é um campo só: tirá-lo deixa a explicação sem o mínimo."""
    saida = SaidaIA.model_validate_json(_saida(tipo="aviso de banco, é seguro"))

    with pytest.raises(SaidaInutilizavel):
        explicacao_da_saida(saida)
