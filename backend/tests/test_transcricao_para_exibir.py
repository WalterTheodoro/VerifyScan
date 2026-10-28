"""A transcrição do print na tela (correção 9.1): link pelo domínio, telefone e e-mail trocados.

Dentro da imagem, o link não é clicável nem fácil de copiar; transcrito, viraria texto pronto para
copiar — um atalho para o golpe que o print não tinha. O texto guardado continua completo: é o que
o motor analisa e o que a pessoa enviou. A troca é só na exibição, e só aqui.
"""

import pytest

from app.api.deps import obter_servico_analise
from app.ocr.leitura import transcricao_marcada, trocar_nas_mensagens
from app.schemas.analise import MensagemDoPrint

para_exibir = obter_servico_analise().para_exibir

# Com hífen que não quebra (U+2011): em 390 px, "[e-mail]" quebrava em "[e-" / "mail]".
EMAIL = "[e\u2011mail]"


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        (
            "Pague em https://bit.ly/lojaexemplo-bf hoje",
            "Pague em [link: bit.ly] hoje",
        ),
        (
            "Acesse www.loja.exemplo.com.br/promo?id=1.",
            "Acesse [link: exemplo.com.br].",
        ),
        ("Ligue 0800 000 0000 agora", "Ligue [telefone] agora"),
        ("Zap (11) 99999-8888 ou +55 11 98888-7777", "Zap [telefone] ou [telefone]"),
        ("Escreva para suporte@golpe-exemplo.com", f"Escreva para {EMAIL}"),
        ("Oi, tudo bem? Te pago amanhã.", "Oi, tudo bem? Te pago amanhã."),
    ],
    ids=["encurtador", "sem-protocolo", "0800", "celular", "e-mail", "sem-nada"],
)
def test_troca_link_telefone_e_email(texto: str, esperado: str) -> None:
    assert para_exibir(texto) == esperado


def test_marca_do_email_tem_hifen_que_nao_quebra() -> None:
    exibido = para_exibir("Escreva para suporte@golpe-exemplo.com")
    assert "\u2011" in exibido
    assert "-" not in exibido


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Abra intent://pagar/#Intent;scheme=pix;end agora", "Abra [link] agora"),
        (
            "Baixe ftp://arquivos.golpe-exemplo.com/boleto.pdf hoje",
            "Baixe [link: golpe-exemplo.com] hoje",
        ),
        # Um IP não é domínio registrável, e o extrator só acha IP com http.
        ("Veja FTP://192.168.0.10/x", "Veja [link]"),
    ],
    ids=["intent-sem-dominio", "ftp-com-dominio", "ftp-com-ip-sem-dominio"],
)
def test_link_de_qualquer_esquema_tambem_sai(texto: str, esperado: str) -> None:
    """O mesmo padrão da limpeza da IA: o que o extrator não procura (só http e https) também é
    link. Sem domínio registrável, `[link]`."""
    assert para_exibir(texto) == esperado


def test_esquema_http_continua_com_o_dominio_e_a_pontuacao() -> None:
    assert para_exibir("Pague em https://bit.ly/x.") == "Pague em [link: bit.ly]."


def test_dominio_do_link_e_o_mesmo_do_bloco_de_links() -> None:
    servico = obter_servico_analise()
    texto = "Rastreie em http://pagamento.correios-rastreio.example/x?id=1"
    [link] = servico.links_do_texto(texto)
    assert para_exibir(texto) == f"Rastreie em [link: {link.dominio}]"


def test_o_dominio_na_marca_nao_e_trocado_de_novo() -> None:
    """`bit.ly` sozinho também é link: a marca `[link: bit.ly]` não pode virar outra marca."""
    texto = "Veja https://bit.ly/abc e também bit.ly/xyz e bit.ly"
    assert para_exibir(texto) == "Veja [link: bit.ly] e também [link: bit.ly] e [link: bit.ly]"


def test_mais_links_que_o_maximo_do_extrator_tambem_saem() -> None:
    """O extrator para em `maximo_por_analise` (20). Na tela, nenhum link pode sobrar."""
    texto = " ".join(f"https://golpe{n}.example/x" for n in range(30))
    exibido = para_exibir(texto)
    assert "https://" not in exibido
    assert exibido.count("[link: ") == 30


def test_link_com_telefone_dentro_vira_uma_marca_so() -> None:
    assert para_exibir("Chame em https://wa.me/5511999998888") == "Chame em [link: wa.me]"


def test_trocar_nas_mensagens_mantem_as_marcas_e_o_que_a_pessoa_escreveu() -> None:
    """O que a pessoa digitou junto é dela, como o "Você colou" do texto: não muda."""
    marcada = transcricao_marcada(
        [
            MensagemDoPrint(de="pessoa", texto="Meu número é 11 99999-8888"),
            MensagemDoPrint(
                de="contato", texto="Pague em https://bit.ly/x\nou ligue 0800 000 0000"
            ),
        ],
        "Recebi de suporte@golpe-exemplo.com",
    )

    assert trocar_nas_mensagens(marcada, para_exibir) == (
        "[enviada pela pessoa]\nMeu número é [telefone]\n\n"
        "[recebida]\nPague em [link: bit.ly]\nou ligue [telefone]\n\n"
        "[a pessoa também escreveu]\nRecebi de suporte@golpe-exemplo.com"
    )
