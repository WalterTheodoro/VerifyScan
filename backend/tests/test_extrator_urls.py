"""URLExtractor — encontrar, isolar e canonicalizar os links do texto (§5.4.2 do RFC).

Na Fase 1 ele não pontua: todo peso de URL (typosquatting, TLD, idade, reputação) pertence ao
DomainAnalyzer e ao URLChecker, das Fases 3 e 4. Aqui só se garante que o link é encontrado e
reduzido a uma forma estável — que é a chave de cache da Fase 4 e a entrada da Fase 3.
"""

import pytest

from app.analyzers.urls import URLExtractor
from app.scoring.regras import carregar_regras


@pytest.fixture
def extrator() -> URLExtractor:
    return URLExtractor(carregar_regras().urls)


def canonicas(extrator: URLExtractor, texto: str) -> list[str]:
    return [url.canonica for url in extrator.extrair(texto)]


# ─── as quatro formas do RFC ──────────────────────────────────────────────────────────────


def test_url_completa(extrator: URLExtractor) -> None:
    (url,) = extrator.extrair("Confira em https://exemplo.com/promo agora")

    assert url.original == "https://exemplo.com/promo"
    assert url.canonica == "https://exemplo.com/promo"
    assert url.host == "exemplo.com"


def test_url_sem_protocolo(extrator: URLExtractor) -> None:
    (url,) = extrator.extrair("Entre em www.banco-seguro.com.br para atualizar")

    assert url.original == "www.banco-seguro.com.br"
    assert url.canonica == "http://www.banco-seguro.com.br/"
    assert url.host == "www.banco-seguro.com.br"


def test_url_encurtada(extrator: URLExtractor) -> None:
    (url,) = extrator.extrair("Segue o link: bit.ly/3xYzAb")

    assert url.original == "bit.ly/3xYzAb"
    assert url.canonica == "http://bit.ly/3xYzAb"
    assert url.host == "bit.ly"


def test_url_embutida_em_texto_corrido(extrator: URLExtractor) -> None:
    """O exemplo literal do RFC: "acesse aqui: site.com"."""
    (url,) = extrator.extrair("Para resolver, acesse aqui: premio-agora.xyz.")

    assert url.original == "premio-agora.xyz"
    assert url.canonica == "http://premio-agora.xyz/"


def test_varias_urls_na_ordem_em_que_aparecem(extrator: URLExtractor) -> None:
    texto = "Primeiro https://a.com, depois www.b.com e por fim c.net/x"

    assert canonicas(extrator, texto) == [
        "https://a.com/",
        "http://www.b.com/",
        "http://c.net/x",
    ]


# ─── forma canônica (ADR-0009) ────────────────────────────────────────────────────────────


def test_host_vira_minusculo_e_o_caminho_nao(extrator: URLExtractor) -> None:
    """O host é insensível a maiúscula; o caminho não é, e mudá-lo mudaria a URL."""
    (url,) = extrator.extrair("https://Exemplo.COM/Caminho/Arquivo")

    assert url.canonica == "https://exemplo.com/Caminho/Arquivo"


def test_fragmento_sai_e_query_fica(extrator: URLExtractor) -> None:
    """O fragmento nunca chega ao servidor; a query pode ser a identidade da página do golpe."""
    (url,) = extrator.extrair("https://exemplo.com/p?id=42&ref=sms#topo")

    assert url.canonica == "https://exemplo.com/p?id=42&ref=sms"


def test_porta_padrao_sai_e_porta_incomum_fica(extrator: URLExtractor) -> None:
    assert canonicas(extrator, "https://exemplo.com:443/a") == ["https://exemplo.com/a"]
    assert canonicas(extrator, "http://exemplo.com:8080/a") == ["http://exemplo.com:8080/a"]


def test_ponto_final_do_host_sai(extrator: URLExtractor) -> None:
    (url,) = extrator.extrair("http://exemplo.com./a")

    assert url.host == "exemplo.com"


def test_usuario_antes_do_arroba_e_descartado(extrator: URLExtractor) -> None:
    """`http://bradesco.com.br@golpe.xyz` vai para golpe.xyz — é vetor de phishing clássico.

    A forma canônica precisa mostrar o host real, senão a Fase 3 analisa o domínio errado.
    """
    (url,) = extrator.extrair("Acesse http://bradesco.com.br@golpe.xyz/pix")

    assert url.host == "golpe.xyz"
    assert url.canonica == "http://golpe.xyz/pix"
    assert url.original == "http://bradesco.com.br@golpe.xyz/pix"


def test_pontuacao_da_frase_nao_entra_na_url(extrator: URLExtractor) -> None:
    assert canonicas(extrator, "veja (exemplo.com/a), ok?") == ["http://exemplo.com/a"]
    assert canonicas(extrator, "entre em exemplo.com!") == ["http://exemplo.com/"]


def test_urls_iguais_apos_canonicalizar_contam_uma_vez(extrator: URLExtractor) -> None:
    texto = "Vá em exemplo.com/a#um ou em EXEMPLO.com/a#dois"

    assert canonicas(extrator, texto) == ["http://exemplo.com/a"]


def test_respeita_o_teto_de_urls_por_analise(extrator: URLExtractor) -> None:
    teto = carregar_regras().urls.maximo_por_analise
    texto = " ".join(f"site{indice}.com" for indice in range(teto + 5))

    assert len(extrator.extrair(texto)) == teto


# ─── negativos: o que NÃO é URL ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "texto",
    [
        pytest.param("O valor é R$ 3,50 apenas", id="valor-em-reais"),
        pytest.param("Rodamos em Python 3.12 aqui", id="numero-de-versao"),
        pytest.param("Segue o arquivo.pdf em anexo", id="nome-de-arquivo"),
        pytest.param("Escreva para contato@banco.com.br", id="endereco-de-email"),
        pytest.param("Obrigado.Att, Maria", id="ponto-final-sem-espaco"),
        pytest.param("Chegou às 14h30.Vamos?", id="hora-colada-na-frase"),
        pytest.param("Fatura de 05/09 no valor combinado", id="data"),
    ],
)
def test_nao_extrai_o_que_nao_e_url(extrator: URLExtractor, texto: str) -> None:
    assert extrator.extrair(texto) == []


def test_email_nao_vira_url_mas_url_na_mesma_frase_sim(extrator: URLExtractor) -> None:
    """O domínio do e-mail é assunto do EmailAnalyzer, não do extrator de links."""
    texto = "Escreva para contato@banco.com.br ou acesse www.banco.com.br"

    assert canonicas(extrator, texto) == ["http://www.banco.com.br/"]


def test_tld_desconhecido_sem_protocolo_nao_e_url(extrator: URLExtractor) -> None:
    """Sem protocolo, só passa TLD da lista — senão qualquer `palavra.palavra` viraria link."""
    assert extrator.extrair("Veja o relatorio.final que mandei") == []


def test_tld_desconhecido_com_protocolo_e_url(extrator: URLExtractor) -> None:
    """Com `http://` explícito não há ambiguidade, e a lista de TLDs não se aplica."""
    (url,) = extrator.extrair("Acesse http://intranet.local/relatorio")

    assert url.host == "intranet.local"


def test_texto_sem_nada_nao_quebra(extrator: URLExtractor) -> None:
    assert extrator.extrair("") == []
