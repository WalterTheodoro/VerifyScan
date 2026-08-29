"""TextAnalyzer — as seis categorias da §5.4.1 do RFC.

Um caso por categoria, mais os negativos. Os negativos são a parte que importa: o falso
positivo constrangedor deste projeto é classificar a mensagem real do banco como golpe.
"""

import pytest

from app.analyzers.texto import TextAnalyzer
from app.schemas.analise import CategoriaFator
from app.scoring.regras import carregar_regras


@pytest.fixture
def analisador() -> TextAnalyzer:
    return TextAnalyzer(carregar_regras())


def categorias(analisador: TextAnalyzer, texto: str) -> set[CategoriaFator]:
    return {fator.categoria for fator in analisador.analisar(texto)}


# ─── um caso por categoria ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("texto", "esperada"),
    [
        ("Aproveite, clique agora.", "urgencia"),
        ("Correios informa que há uma novidade para você.", "personificacao_marca"),
        ("Sua conta será suspensa em breve.", "ameaca_bloqueio"),
        ("Parabéns! Você ganhou um brinde.", "premio_falso"),
        ("Faça um PIX para concluir.", "solicitacao_financeira"),
        ("Confirme seu CPF para continuar.", "dados_pessoais"),
    ],
)
def test_cada_categoria_dispara_com_seu_padrao(
    analisador: TextAnalyzer, texto: str, esperada: CategoriaFator
) -> None:
    assert categorias(analisador, texto) == {esperada}


def test_fator_carrega_tipo_peso_e_descricao(analisador: TextAnalyzer) -> None:
    (fator,) = analisador.analisar("Faça um PIX para concluir.")

    assert fator.tipo == "texto"
    assert fator.categoria == "solicitacao_financeira"
    assert fator.peso == 25  # §5.4.1
    assert fator.descricao == "A mensagem pede um pagamento, transferência ou comprovante."


def test_normalizacao_faz_acento_maiuscula_e_quebra_de_linha_nao_importarem(
    analisador: TextAnalyzer,
) -> None:
    texto = "ÚLTIMAS\n   HORAS para resgatar seu PRÊMIO"

    assert categorias(analisador, texto) == {"urgencia", "premio_falso"}


def test_categoria_com_varios_padroes_casando_gera_um_fator_so(analisador: TextAnalyzer) -> None:
    """ADR-0004: agregação por categoria. Repetir a frase não pode mudar o resultado."""
    texto = "Clique agora! Expira em 1 hora, últimas horas, prazo vencendo, é urgente!"

    fatores = [fator for fator in analisador.analisar(texto) if fator.categoria == "urgencia"]

    assert len(fatores) == 1


# ─── negativos: o que NÃO pode pontuar ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "texto",
    [
        pytest.param(
            "Oi, tudo bem? Consegue me mandar aquele documento à tarde?",
            id="conversa-comum",
        ),
        pytest.param(
            "Banco do Brasil: compra aprovada no seu cartão final 1234, R$ 89,90 em "
            "Supermercado São José. Não reconhece? Fale com a gente pelo aplicativo.",
            id="compra-aprovada-legitima",
        ),
        pytest.param(
            "Sua fatura do cartão final 1234 fecha em 05/09 e vence em 12/09. "
            "Consulte os valores pelo aplicativo ou nas agências.",
            id="fatura-legitima",
        ),
        pytest.param(
            "Condomínio Edifício Aurora: o boleto de agosto está disponível na portaria. "
            "Vencimento no dia 10.",
            id="boleto-de-condominio",
        ),
        pytest.param(
            "O Banco do Brasil nunca pede seus dados bancários por telefone ou SMS.",
            id="aviso-antifraude-do-proprio-banco",
        ),
    ],
)
def test_mensagem_legitima_nao_gera_fator(analisador: TextAnalyzer, texto: str) -> None:
    assert analisador.analisar(texto) == []


def test_texto_vazio_nao_gera_fator(analisador: TextAnalyzer) -> None:
    assert analisador.analisar("   ") == []


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Falso positivo conhecido — achado 1 de docs/analise-rfc-v1.1.md. Este SMS legítimo "
        "soma 15+15+10=40 e cai em MÉDIO, que conta como golpe na métrica (ADR-0005). O "
        "conserto é a calibração de pesos e faixas na Fase 2; quando ela acontecer, este "
        "teste passa e o strict=True avisa que a pendência fechou."
    ),
)
def test_sms_legitimo_de_banco_nao_deveria_pontuar(analisador: TextAnalyzer) -> None:
    texto = "Banco do Brasil informa: sua conta será suspensa. Clique agora para regularizar."

    assert analisador.analisar(texto) == []


# ─── invariante 1: a descrição nunca carrega o texto do usuário ───────────────────────────


def test_descricao_do_fator_sempre_corresponde_a_um_template_do_yaml() -> None:
    """ADR-0004: descrição é template versionado, não texto gerado no código."""
    regras = carregar_regras()
    analisador = TextAnalyzer(regras)
    texto = "URGENTE: Correios informa que sua conta será bloqueada. Faça um PIX e informe o CPF."

    for fator in analisador.analisar(texto):
        modelo = next(c.descricao for c in regras.categorias if c.id == fator.categoria)
        assert modelo.corresponde(fator.descricao)


def test_descricao_nao_contem_trecho_da_mensagem(analisador: TextAnalyzer) -> None:
    """Se um dia alguém interpolar o trecho casado na descrição, este teste quebra."""
    texto = "URGENTE: faça um PIX para XYZZY4242 e confirme seu CPF agora."

    for fator in analisador.analisar(texto):
        assert "XYZZY4242" not in fator.descricao
