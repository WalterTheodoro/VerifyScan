"""As ferramentas da medição de prints (fatia 9, ADR-0023): sorteio, gabarito e taxa de erro.

Nada aqui desenha imagem nem chama a API: o Playwright e a Anthropic ficam nos scripts, fora do CI.
"""

from collections import Counter

from tools.avaliar_corpus import carregar_corpus
from tools.avaliar_prints import taxa_de_erro_por_caractere
from tools.gerar_prints import (
    INJECAO,
    QUANTIDADE_NO_TESTE,
    QUANTIDADE_POR_ROTULO,
    html_do_print,
    mensagens_esperadas,
    montar_lista,
)
from tools.sortear_divisao import PASTA_CASOS

CASOS = {caso.id: caso for caso in carregar_corpus(PASTA_CASOS)}


def test_lista_sai_so_da_calibracao_e_e_deterministica() -> None:
    lista = montar_lista(list(CASOS.values()))
    assert lista == montar_lista(list(CASOS.values()))
    assert all(CASOS[item["caso"]].divisao == "calibracao" for item in lista)


def test_lista_tem_a_composicao_pedida() -> None:
    lista = montar_lista(list(CASOS.values()))
    tipos = Counter(item["tipo"] for item in lista)
    assert tipos == {"normal": 2 * QUANTIDADE_POR_ROTULO, "injecao": 3, "ilegivel": 2}
    normais = [item for item in lista if item["tipo"] == "normal"]
    assert Counter(CASOS[item["caso"]].rotulo for item in normais) == {
        "golpe": QUANTIDADE_POR_ROTULO,
        "legitimo": QUANTIDADE_POR_ROTULO,
    }
    assert len({item["id"] for item in lista}) == len(lista)
    # Cada variação aparece dos dois lados.
    for campo in ("remetente", "aviso", "primeira", "tema"):
        assert len({item[campo] for item in normais}) == 2, campo


def test_lista_do_teste_sai_so_do_teste_e_nao_cruza_com_a_calibracao() -> None:
    """A medida limpa: 10 golpes e 10 legítimas da divisão teste, ids próprios."""
    teste = montar_lista(list(CASOS.values()), "teste")
    calibracao = montar_lista(list(CASOS.values()))

    assert all(CASOS[item["caso"]].divisao == "teste" for item in teste)
    assert Counter(item["rotulo"] for item in teste) == {
        "golpe": QUANTIDADE_NO_TESTE,
        "legitimo": QUANTIDADE_NO_TESTE,
    }
    assert {item["tipo"] for item in teste} == {"normal"}
    assert all(item["id"].startswith("t") for item in teste)
    assert not {item["caso"] for item in teste} & {item["caso"] for item in calibracao}


def test_aviso_do_app_so_com_numero_nao_salvo() -> None:
    for item in montar_lista(list(CASOS.values())):
        if item["aviso"] == "sim":
            assert item["remetente"] == "numero"


def test_mensagens_esperadas_trazem_as_anteriores_e_a_injecao() -> None:
    lista = montar_lista(list(CASOS.values()))
    injecao = next(item for item in lista if item["tipo"] == "injecao")
    mensagens = mensagens_esperadas(injecao, CASOS[injecao["caso"]])
    assert mensagens[-1][0] == "contato"
    assert mensagens[-1][1].endswith(INJECAO)

    andamento = next(i for i in lista if i["primeira"] == "nao" and i["tipo"] == "normal")
    mensagens = mensagens_esperadas(andamento, CASOS[andamento["caso"]])
    assert len(mensagens) >= 2
    assert mensagens[-1] == ("contato", CASOS[andamento["caso"]].conteudo)


def test_html_e_generico_sem_marca_de_aplicativo() -> None:
    lista = montar_lista(list(CASOS.values()))
    for item in lista[:6]:
        html = html_do_print(item, CASOS[item["caso"]]).lower()
        for marca in ("whatsapp", "instagram", "telegram", "messenger", "gmail", "outlook"):
            # A marca pode estar no texto da mensagem do corpus, nunca no desenho.
            assert html.count(marca) == CASOS[item["caso"]].conteudo.lower().count(marca), marca


def test_taxa_de_erro_por_caractere() -> None:
    assert taxa_de_erro_por_caractere("Pague a taxa", "Pague a taxa") == 0.0
    assert taxa_de_erro_por_caractere("Pague  a\ntaxa", "Pague a taxa") == 0.0
    assert taxa_de_erro_por_caractere("Pague a taxo", "Pague a taxa") == 1 / 12
    assert taxa_de_erro_por_caractere("", "abcd") == 1.0
    assert taxa_de_erro_por_caractere("abcdefgh", "abcd") == 1.0
