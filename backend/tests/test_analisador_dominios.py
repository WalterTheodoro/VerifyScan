"""DomainAnalyzer — sinais léxicos sobre os links da mensagem (Fase 3, ADR-0022).

O analisador nunca abre o link: nem GET, nem HEAD, nem DNS. Tudo aqui é sobre o texto do
endereço, e por isso cada teste é uma string, sem rede (CLAUDE.md §6).

Os negativos importam tanto quanto os positivos: o link do site oficial do banco não pode
pontuar, e "inter" não pode casar com "internet".
"""

import pytest

from app.analyzers.dominios import DomainAnalyzer
from app.analyzers.urls import URLExtractor
from app.schemas.analise import CategoriaFator
from app.scoring.motor import ScoringEngine
from app.scoring.regras import CATEGORIAS_DE_LINK, carregar_regras


@pytest.fixture
def analisador() -> DomainAnalyzer:
    return DomainAnalyzer(carregar_regras())


@pytest.fixture
def extrator() -> URLExtractor:
    return URLExtractor(carregar_regras().urls)


def categorias(
    analisador: DomainAnalyzer, extrator: URLExtractor, texto: str
) -> set[CategoriaFator]:
    return {fator.categoria for fator in analisador.analisar(extrator.extrair(texto))}


# ─── um caso por sinal ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("texto", "esperada"),
    [
        ("Veja: https://bit.ly/abc123", "link_encurtado"),
        ("Veja: https://encurtador.com.br/xYz", "link_encurtado"),
        ("Acesse http://192.168.10.5/pagina", "link_ip"),
        ("Acesse https://203.0.113.9/pagina", "link_ip"),
        ("Confirme em https://xn--nubnk-sqa.example/confirmar", "link_caracteres_enganosos"),
        ("Acesse https://libera\u200bcao.example", "link_caracteres_enganosos"),
        ("Acesse https://it\u0430u.example", "link_caracteres_enganosos"),  # "a" cirílico
        ("Pague em https://correios-rastreio.example/pagar", "link_marca_nao_oficial"),
        ("Acesse https://bradesco.conta-segura.com/", "link_marca_nao_oficial"),
        ("Acesse https://bradesc0.com/", "link_parecido_com_oficial"),
        ("Acesse https://ltau.com.br/", "link_parecido_com_oficial"),
        ("Acesse https://nubamk.com.br/", "link_parecido_com_oficial"),
        ("Acesse https://premio-agora.help/", "link_tld_abusado"),
        ("Acesse https://loja-qualquer.example/atualizacao", "link_palavra_isca"),
        ("Acesse https://regulariza-cpf.example/", "link_palavra_isca"),
        ("Acesse http://site-comum.example/", "link_sem_https"),
        ("Acesse https://site-comum.example@outro-site.example/", "link_truque_endereco"),
        ("Acesse https://site-comum.example:8443/", "link_truque_endereco"),
        ("Acesse https://a.b.c.site-comum.example/", "link_truque_endereco"),
    ],
)
def test_cada_sinal_dispara(
    analisador: DomainAnalyzer, extrator: URLExtractor, texto: str, esperada: CategoriaFator
) -> None:
    assert esperada in categorias(analisador, extrator, texto)


def test_todo_sinal_do_yaml_tem_um_caso_acima() -> None:
    """Se uma categoria de link entrar sem teste de disparo, este teste avisa."""
    cobertas = {
        "link_encurtado",
        "link_ip",
        "link_caracteres_enganosos",
        "link_marca_nao_oficial",
        "link_parecido_com_oficial",
        "link_tld_abusado",
        "link_palavra_isca",
        "link_sem_https",
        "link_truque_endereco",
    }
    assert cobertas == set(CATEGORIAS_DE_LINK)


def test_fator_de_link_tem_tipo_dominio_peso_e_marca_na_descricao(
    analisador: DomainAnalyzer, extrator: URLExtractor
) -> None:
    [fator] = analisador.analisar(extrator.extrair("https://correios-rastreio.example/"))

    assert fator.tipo == "dominio"
    assert fator.categoria == "link_marca_nao_oficial"
    assert fator.peso == 35
    assert "Correios" in fator.descricao


# ─── negativos: domínio oficial e site comum não pontuam ─────────────────────────────────


@pytest.mark.parametrize(
    "texto",
    [
        pytest.param("Acompanhe em https://rastreamento.correios.com.br", id="correios-oficial"),
        pytest.param("Acesse https://www.bradesco.com.br/seguranca", id="isca-em-dominio-oficial"),
        pytest.param("Consulte em https://www.gov.br/inss", id="gov-br"),
        pytest.param("Consulte em https://www.detran.sp.gov.br", id="detran-estadual"),
        pytest.param("Veja em https://www.caixa.gov.br/fgts", id="caixa"),
        pytest.param("Detalhes em nubank.com.br/cartao", id="sem-protocolo-oficial"),
        pytest.param("Saiba mais em https://www.catolicasc.org.br", id="gate-3-catolica"),
        pytest.param("Pedido em https://loja-exemplo.example/pedidos/48213", id="loja-comum"),
        pytest.param("Leia em https://internet-rapida.example/planos", id="inter-nao-e-internet"),
        pytest.param("Veja https://www.portoseguro.com.br", id="seguro-nao-e-seguranca"),
    ],
)
def test_link_legitimo_nao_gera_fator(
    analisador: DomainAnalyzer, extrator: URLExtractor, texto: str
) -> None:
    assert analisador.analisar(extrator.extrair(texto)) == []


def test_gov_br_escrito_como_texto_nao_e_http_sem_s(
    analisador: DomainAnalyzer, extrator: URLExtractor
) -> None:
    """O extrator completa "gov.br" com `http://`. Quem não digitou o http não levou o sinal."""
    assert analisador.analisar(extrator.extrair("Consulte no gov.br, pelo app.")) == []


def test_sem_link_nao_gera_fator(analisador: DomainAnalyzer) -> None:
    assert analisador.analisar([]) == []


# ─── a forma do endereço ──────────────────────────────────────────────────────────────────


def test_marca_exata_e_marca_nao_oficial_nao_parecida(
    analisador: DomainAnalyzer, extrator: URLExtractor
) -> None:
    """`inss-provadevida` usa o nome inteiro: é marca fora do domínio oficial, não imitação."""
    achadas = categorias(analisador, extrator, "https://inss-provadevida.example")

    assert "link_marca_nao_oficial" in achadas
    assert "link_parecido_com_oficial" not in achadas


def test_punycode_que_imita_marca_conta_como_parecido(
    analisador: DomainAnalyzer, extrator: URLExtractor
) -> None:
    """`xn--nubnk-zqa` é "nubánk": só vira "nubank" depois de tirar o acento — é imitação."""
    achadas = categorias(analisador, extrator, "https://xn--nubnk-zqa.example/confirmar")

    assert {"link_caracteres_enganosos", "link_parecido_com_oficial"} <= achadas


def test_digito_no_lugar_de_letra_nao_esconde_a_isca(
    analisador: DomainAnalyzer, extrator: URLExtractor
) -> None:
    assert "link_palavra_isca" in categorias(
        analisador, extrator, "https://regu1ariza-cpf.examp1e/atendimento"
    )


def test_nome_curto_nao_entra_na_comparacao_por_semelhanca(
    analisador: DomainAnalyzer, extrator: URLExtractor
) -> None:
    """ "bb" e "gov" a uma letra de distância casariam com metade da internet."""
    assert categorias(analisador, extrator, "https://bd.example/ https://gol.example/") == set()


def test_palavra_comum_so_casa_por_igualdade(
    analisador: DomainAnalyzer, extrator: URLExtractor
) -> None:
    """ "inter" e "caixa" são palavras: "intel" e "caixas" não podem virar imitação."""
    achadas = categorias(analisador, extrator, "https://intel.example/ https://caixas.example/")

    assert "link_parecido_com_oficial" not in achadas


def test_cada_categoria_pontua_uma_vez_mesmo_com_varios_links(
    analisador: DomainAnalyzer, extrator: URLExtractor
) -> None:
    texto = "https://bit.ly/a https://tinyurl.com/b https://cutt.ly/c"

    fatores = analisador.analisar(extrator.extrair(texto))

    assert [fator.categoria for fator in fatores] == ["link_encurtado"]


# ─── avaliação por link (o que a tela mostra, item 2 da fatia 8) ─────────────────────────


def test_avaliar_devolve_o_dominio_registravel(
    analisador: DomainAnalyzer, extrator: URLExtractor
) -> None:
    [url] = extrator.extrair("https://login.seguro.correios-rastreio.example/taxa?id=42")

    assert analisador.avaliar(url).dominio == "correios-rastreio.example"


def test_avaliar_reconhece_dominio_oficial(
    analisador: DomainAnalyzer, extrator: URLExtractor
) -> None:
    [url] = extrator.extrair("https://rastreamento.correios.com.br/app")

    avaliacao = analisador.avaliar(url)

    assert avaliacao.dominio == "correios.com.br"
    assert avaliacao.oficial_de == "Correios"
    assert avaliacao.sinais == ()


# ─── invariante 1 e privacidade ───────────────────────────────────────────────────────────


def test_descricao_de_link_nunca_traz_o_endereco(
    analisador: DomainAnalyzer, extrator: URLExtractor
) -> None:
    """Decisão da fatia 8: o fator vai para o banco também em análise anônima, então ele traz
    só a marca, da lista fechada, e nunca o domínio da mensagem."""
    texto = (
        "http://correios-xyzzy.help:8080/taxa https://bit.ly/xyzzy https://bradesc0-xyzzy.com "
        "https://xn--nubnk-sqa.example https://1.2.3.4/xyzzy"
    )

    fatores = analisador.analisar(extrator.extrair(texto))

    assert fatores
    for fator in fatores:
        assert "xyzzy" not in fator.descricao


def test_descricao_corresponde_ao_template_do_yaml(
    analisador: DomainAnalyzer, extrator: URLExtractor
) -> None:
    regras = carregar_regras()
    texto = "http://correios-rastreio.help/taxa https://bradesc0.com https://bit.ly/x"

    for fator in analisador.analisar(extrator.extrair(texto)):
        modelo = next(s.descricao for s in regras.dominios.sinais if s.id == fator.categoria)
        assert modelo.corresponde(fator.descricao)


# ─── Gate 3 do plano de execução ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("link", "nivel"),
    [
        ("https://bradesc0.com", "MEDIO"),
        ("https://bradesco.conta-segura.com", "MEDIO"),
        ("https://bradesco.com.br", "BAIXO"),
        ("https://catolicasc.org.br", "BAIXO"),
    ],
)
def test_gate_3_so_pelo_link(
    analisador: DomainAnalyzer, extrator: URLExtractor, link: str, nivel: str
) -> None:
    """Sem nenhum sinal de texto: o link sozinho leva os golpes do gate a MÉDIO e deixa os
    legítimos em BAIXO. `premio-agora.xyz` saiu do gate: .xyz não está entre as terminações
    com concentração alta de spam na fonte do ADR-0022 (ver o diário da fatia 8)."""
    motor = ScoringEngine(carregar_regras())

    resultado = motor.pontuar(analisador.analisar(extrator.extrair(link)))

    assert resultado.nivel_risco == nivel


@pytest.mark.parametrize(
    ("link", "dono"),
    [
        ("https://www.gov.br/inss", "gov.br"),
        ("https://www.detran.sp.gov.br", "gov.br"),
        ("https://www.caixa.gov.br/fgts", "Caixa"),
    ],
)
def test_varias_marcas_sob_gov_br_ficam_com_o_oficial_mais_especifico(
    analisador: DomainAnalyzer, extrator: URLExtractor, link: str, dono: str
) -> None:
    [url] = extrator.extrair(link)

    assert analisador.avaliar(url).oficial_de == dono


# ─── o que a tela mostra no lugar do link (item 2 da fatia 8) ────────────────────────────


def test_descrever_mostra_so_o_dominio_registravel_e_o_que_se_achou(
    analisador: DomainAnalyzer, extrator: URLExtractor
) -> None:
    urls = extrator.extrair("Pague em https://login.correios-rastreio.example/taxa?id=42")

    [link] = analisador.descrever(urls)

    assert link.dominio == "correios-rastreio.example"
    assert link.observacoes == [
        "usa o nome Correios, mas não é um endereço oficial",
        "usa palavras comuns em golpes",
    ]


def test_descrever_nunca_traz_caminho_query_nem_subdominio(
    analisador: DomainAnalyzer, extrator: URLExtractor
) -> None:
    urls = extrator.extrair("https://login.seguro.golpe-xyzzy.example/pagar?cpf=42#fim")

    [link] = analisador.descrever(urls)

    texto = link.dominio + " ".join(link.observacoes)
    for trecho in ("login", "seguro.", "/pagar", "cpf=42", "fim", "https"):
        assert trecho not in texto


def test_descrever_dominio_oficial(analisador: DomainAnalyzer, extrator: URLExtractor) -> None:
    [link] = analisador.descrever(extrator.extrair("https://rastreamento.correios.com.br"))

    assert (link.dominio, link.observacoes) == ("correios.com.br", ["endereço oficial: Correios"])
    assert link.oficial is True


def test_conselho_do_link_oficial_nao_e_o_do_golpe(
    analisador: DomainAnalyzer, extrator: URLExtractor
) -> None:
    """Fatia 9, item 12: o fecho do bloco de links não pode mandar "não abra antes de confirmar"
    um endereço oficial. As duas frases vêm do `regras.yaml`."""
    regras = carregar_regras().dominios
    [oficial] = analisador.descrever(extrator.extrair("https://rastreamento.correios.com.br"))
    [golpe] = analisador.descrever(extrator.extrair("https://correios-taxa.example/pagar"))
    [sem_sinal] = analisador.descrever(extrator.extrair("https://loja-exemplo.example/pedido"))

    assert oficial.conselho == regras.link_conselho_oficial
    assert "O endereço é oficial" in oficial.conselho
    assert "Não abra" not in oficial.conselho
    assert golpe.conselho == sem_sinal.conselho == regras.link_conselho
    assert (golpe.oficial, sem_sinal.oficial) == (False, False)


def test_descrever_link_sem_sinal_nao_diz_que_e_seguro(
    analisador: DomainAnalyzer, extrator: URLExtractor
) -> None:
    [link] = analisador.descrever(extrator.extrair("https://loja-exemplo.example/pedido"))

    assert link.observacoes == [
        "nada estranho no endereço, mas isso não garante que o site é verdadeiro"
    ]


def test_descrever_junta_links_do_mesmo_dominio(
    analisador: DomainAnalyzer, extrator: URLExtractor
) -> None:
    texto = "https://a.golpe-xyz.example/1 e https://golpe-xyz.example/taxa e https://bit.ly/x"

    links = analisador.descrever(extrator.extrair(texto))

    assert [link.dominio for link in links] == ["golpe-xyz.example", "bit.ly"]
    assert links[0].observacoes == ["usa palavras comuns em golpes"]
