"""`scoring/regras.yaml` — carregamento, validação e o mecanismo de template das descrições.

Este arquivo é o guarda da invariante 5 do CLAUDE.md: peso e padrão são dado versionado, não
número mágico em `.py`. Os pesos conferidos aqui vêm da §5.4.1 do RFC (p. 22-23).
"""

import re
from typing import get_args

import pytest
from pydantic import ValidationError

from app.schemas.analise import CategoriaFator
from app.scoring.descricoes import PLACEHOLDERS_PERMITIDOS, ModeloDescricao
from app.scoring.regras import CATEGORIAS_DE_LINK, CATEGORIAS_DE_TEXTO, Regras, carregar_regras

# §5.4.1 do RFC, tabela "Categoria / Exemplos de padrões detectados / Peso".
PESOS_DO_RFC = {
    "urgencia": 10,
    "personificacao_marca": 15,
    "ameaca_bloqueio": 15,
    "premio_falso": 20,
    "solicitacao_financeira": 25,
    "dados_pessoais": 25,
}
# Fora do RFC (ADR-0020): sozinha leva a ALTO, então o peso é o primeiro ponto acima de MÉDIO.
PESOS = {**PESOS_DO_RFC, "instrucao_ao_analisador": 61}

# Sinais de link (ADR-0022). Do RFC: typosquatting +35, TLD de alto risco +15. "Marca no
# endereço" é o subdomínio enganoso (+30) subido a 35 para que, sozinho, saia de BAIXO.
PESOS_DE_LINK = {
    "link_marca_nao_oficial": 35,
    "link_parecido_com_oficial": 35,
    "link_caracteres_enganosos": 35,
    "link_ip": 35,
    "link_truque_endereco": 25,
    "link_encurtado": 15,
    "link_tld_abusado": 15,
    "link_palavra_isca": 15,
    "link_sem_https": 10,
}


def test_regras_carregam_do_yaml() -> None:
    regras = carregar_regras()

    assert regras.versao >= 1
    assert regras.agregacao == "por_categoria"


def test_as_seis_categorias_existem_com_os_pesos_do_rfc() -> None:
    """§5.4.1 tem seis categorias; a §5.4.7 funde duas delas — e está errada (errata, item 3).
    A sétima, `instrucao_ao_analisador`, não é do RFC (ADR-0020)."""
    regras = carregar_regras()

    assert {categoria.id: categoria.peso for categoria in regras.categorias} == PESOS


def test_instrucao_ao_analisador_sozinha_leva_a_alto() -> None:
    """Mensagem legítima não fala com um analisador: o peso tem que passar do teto de MÉDIO,
    ou uma recalibração das faixas deixaria a injeção sair MÉDIO com a IA fora do ar."""
    regras = carregar_regras()
    [categoria] = [c for c in regras.categorias if c.id == "instrucao_ao_analisador"]

    assert regras.faixas.classificar(categoria.peso) == "ALTO"


def test_sinais_de_link_existem_com_os_pesos_propostos() -> None:
    regras = carregar_regras()

    assert {sinal.id: sinal.peso for sinal in regras.dominios.sinais} == PESOS_DE_LINK


def test_categorias_de_texto_e_de_link_cobrem_o_contrato_sem_sobrepor() -> None:
    """Toda categoria do contrato é de texto ou de link, nunca das duas."""
    assert set(CATEGORIAS_DE_TEXTO) | set(CATEGORIAS_DE_LINK) == set(get_args(CategoriaFator))
    assert not set(CATEGORIAS_DE_TEXTO) & set(CATEGORIAS_DE_LINK)


def test_marca_fora_do_oficial_e_imitacao_sozinhas_saem_de_baixo() -> None:
    """Link com o nome da marca fora do domínio oficial é o golpe típico: sozinho, MÉDIO."""
    regras = carregar_regras()
    pesos = {sinal.id: sinal.peso for sinal in regras.dominios.sinais}

    for categoria in ("link_marca_nao_oficial", "link_parecido_com_oficial"):
        assert regras.faixas.classificar(pesos[categoria]) == "MEDIO"


def test_descricao_de_link_so_usa_a_marca() -> None:
    """Fatia 8: o fator vai para o banco também em análise anônima, então o domínio da mensagem
    não entra na descrição — só o nome da marca, que vem da lista fechada."""
    for sinal in carregar_regras().dominios.sinais:
        assert sinal.descricao.placeholders <= {"marca"}


def test_toda_terminacao_abusada_e_extraida_sem_protocolo() -> None:
    """Sem isso, `golpe.cfd` escrito sem `http://` nem chegaria ao DomainAnalyzer."""
    regras = carregar_regras()

    assert regras.dominios.tlds_abusados <= regras.urls.tlds_conhecidos


def test_faixas_sao_as_do_rfc() -> None:
    """§5.4.7: 0-30 BAIXO, 31-60 MÉDIO, 61+ ALTO."""
    faixas = carregar_regras().faixas

    assert (faixas.baixo_ate, faixas.medio_ate) == (30, 60)


def test_toda_categoria_tem_padrao_e_todo_padrao_compila() -> None:
    """Pydantic compila as regex no carregamento: YAML quebrado derruba o boot, não o request."""
    for categoria in carregar_regras().categorias:
        assert categoria.padroes, f"categoria sem padrão: {categoria.id}"
        for padrao in categoria.padroes:
            assert isinstance(padrao, re.Pattern)


def test_padroes_estao_normalizados() -> None:
    """O mesmo normalizador roda no texto e no padrão — por isso nenhum padrão tem acento."""
    for categoria in carregar_regras().categorias:
        for padrao in categoria.padroes:
            assert padrao.pattern == padrao.pattern.lower()
            assert not any(caractere in padrao.pattern for caractere in "áàâãéêíóôõúüç")


def test_toda_descricao_usa_apenas_placeholders_do_conjunto_fechado() -> None:
    """ADR-0004: a descrição é template, preenchido só por valor tipado — nunca texto do usuário."""
    for categoria in carregar_regras().categorias:
        assert categoria.descricao.placeholders <= PLACEHOLDERS_PERMITIDOS


# ─── mecanismo de template ────────────────────────────────────────────────────────────────
# A Fase 1 só usa texto fixo, mas o mecanismo existe desde já: a Fase 3 precisa de
# `{dominio}` e `{engines}`, e o teste da invariante 1 (ADR-0004) só significa alguma coisa
# se houver como conferir uma descrição contra o template que a gerou.


def test_template_sem_placeholder_renderiza_como_esta() -> None:
    modelo = ModeloDescricao.model_validate("A mensagem pressiona você a agir com pressa.")

    assert modelo.placeholders == frozenset()
    assert modelo.renderizar() == "A mensagem pressiona você a agir com pressa."


def test_template_com_placeholder_renderiza_com_valor_tipado() -> None:
    modelo = ModeloDescricao.model_validate("O endereço {dominio} imita uma marca conhecida.")

    assert modelo.placeholders == {"dominio"}
    assert modelo.renderizar({"dominio": "bradesc0.com"}) == (
        "O endereço bradesc0.com imita uma marca conhecida."
    )


def test_template_recusa_placeholder_fora_do_conjunto_fechado() -> None:
    """`{texto}` é exatamente o que a invariante 1 proíbe: trecho do usuário na descrição."""
    with pytest.raises(ValidationError, match="placeholder"):
        ModeloDescricao.model_validate("A mensagem diz: {texto}")


def test_renderizar_exige_todos_os_placeholders_declarados() -> None:
    modelo = ModeloDescricao.model_validate("Domínio {dominio}, {engines} sistemas.")

    with pytest.raises(KeyError):
        modelo.renderizar({"dominio": "x.com"})


def test_descricao_renderizada_confere_contra_o_template() -> None:
    """Ferramenta do teste da invariante 1: dada uma descrição, ela veio de algum template?"""
    modelo = ModeloDescricao.model_validate("O endereço {dominio} imita uma marca conhecida.")

    assert modelo.corresponde("O endereço bradesc0.com imita uma marca conhecida.")
    assert not modelo.corresponde("O endereço imita uma marca conhecida.")
    assert not modelo.corresponde("Qualquer outra frase.")


# ─── validação: YAML errado não passa ─────────────────────────────────────────────────────
# O `regras.yaml` é editado à mão a cada recalibração (Fase 2). Estes testes são o que garante
# que um erro de edição derruba o boot com mensagem clara, em vez de virar peso silenciosamente
# errado numa análise.

Categoria = dict[str, object]


def _regras_validas() -> dict[str, object]:
    categorias: list[Categoria] = [
        {"id": id_, "peso": peso, "descricao": "Descrição.", "padroes": ["teste"]}
        for id_, peso in PESOS.items()
    ]
    return {
        "versao": 1,
        "agregacao": "por_categoria",
        "faixas": {"baixo_ate": 30, "medio_ate": 60},
        "urls": {"maximo_por_analise": 20, "tlds_conhecidos": ["com", "br", "top"]},
        "categorias": categorias,
        "dominios": _dominios_validos(),
    }


def _dominios_validos() -> dict[str, object]:
    return {
        "sinais": [
            {"id": id_, "peso": peso, "descricao": "Descrição.", "no_link": "frase"}
            for id_, peso in PESOS_DE_LINK.items()
        ],
        "link_oficial": "endereço oficial: {marca}",
        "link_sem_sinal": "nada estranho",
        "link_conselho": "Não abra antes de confirmar.",
        "link_conselho_oficial": "O endereço é oficial.",
        "encurtadores": ["bit.ly"],
        "tlds_abusados": ["top"],
        "palavras_isca": ["taxa"],
        "portas_comuns": [80, 443],
        "subdominios_suspeitos_a_partir_de": 3,
        "semelhanca": {
            "minimo_de_letras": 4,
            "curto_ate": 6,
            "distancia_curto": 1,
            "distancia_longo": 2,
        },
        "marcas": [
            {
                "nome": "Correios",
                "nomes": ["correios"],
                "semelhanca": True,
                "oficiais": ["correios.com.br"],
            },
        ],
    }


def _dominios(dados: dict[str, object]) -> dict[str, object]:
    dominios = dados["dominios"]
    assert isinstance(dominios, dict)
    return dominios


def _lista(dados: dict[str, object], chave: str) -> list[dict[str, object]]:
    lista = _dominios(dados)[chave]
    assert isinstance(lista, list)
    return lista


def _primeira_categoria(dados: dict[str, object]) -> Categoria:
    categorias = dados["categorias"]
    assert isinstance(categorias, list)
    primeira: Categoria = categorias[0]
    return primeira


def test_yaml_valido_no_formato_do_arquivo_real_passa() -> None:
    assert Regras.model_validate(_regras_validas()).versao == 1


def test_recusa_categoria_faltando() -> None:
    dados = _regras_validas()
    categorias = dados["categorias"]
    assert isinstance(categorias, list)
    dados["categorias"] = categorias[:-1]

    with pytest.raises(ValidationError, match="instrucao_ao_analisador"):
        Regras.model_validate(dados)


def test_recusa_categoria_desconhecida() -> None:
    dados = _regras_validas()
    categorias = dados["categorias"]
    assert isinstance(categorias, list)
    categorias.append({"id": "inventada", "peso": 5, "descricao": "x", "padroes": ["a"]})

    with pytest.raises(ValidationError, match="inventada"):
        Regras.model_validate(dados)


def test_recusa_categoria_repetida() -> None:
    dados = _regras_validas()
    categorias = dados["categorias"]
    assert isinstance(categorias, list)
    categorias.append(dict(_primeira_categoria(dados)))

    with pytest.raises(ValidationError, match="repetida"):
        Regras.model_validate(dados)


def test_recusa_regex_invalida() -> None:
    dados = _regras_validas()
    _primeira_categoria(dados)["padroes"] = ["a("]

    with pytest.raises(ValidationError):
        Regras.model_validate(dados)


def test_recusa_faixas_invertidas() -> None:
    dados = _regras_validas()
    dados["faixas"] = {"baixo_ate": 60, "medio_ate": 30}

    with pytest.raises(ValidationError, match="faixa"):
        Regras.model_validate(dados)


def test_recusa_peso_nao_positivo() -> None:
    dados = _regras_validas()
    _primeira_categoria(dados)["peso"] = 0

    with pytest.raises(ValidationError):
        Regras.model_validate(dados)


def test_recusa_classe_de_regex_maiuscula() -> None:
    r"""`\D` vira `\d` no `.lower()` da normalização: a regex continua compilando e passa a
    significar o oposto. Falhar no boot é melhor que um padrão silenciosamente invertido."""
    dados = _regras_validas()
    _primeira_categoria(dados)["padroes"] = [r"pix de \D+"]

    with pytest.raises(ValidationError, match="maiúscula"):
        Regras.model_validate(dados)


def test_recusa_sinal_de_link_faltando() -> None:
    dados = _regras_validas()
    _dominios(dados)["sinais"] = _lista(dados, "sinais")[:-1]

    with pytest.raises(ValidationError, match="link_sem_https"):
        Regras.model_validate(dados)


def test_recusa_categoria_de_link_na_secao_de_texto() -> None:
    dados = _regras_validas()
    categorias = dados["categorias"]
    assert isinstance(categorias, list)
    categorias.append({"id": "link_ip", "peso": 5, "descricao": "x", "padroes": ["a"]})

    with pytest.raises(ValidationError, match="link_ip"):
        Regras.model_validate(dados)


def test_recusa_dominio_na_descricao_de_link() -> None:
    dados = _regras_validas()
    _lista(dados, "sinais")[0]["descricao"] = "O endereço {dominio} usa a marca {marca}."

    with pytest.raises(ValidationError, match="dominio"):
        Regras.model_validate(dados)


def test_recusa_terminacao_abusada_que_o_extrator_nao_conhece() -> None:
    dados = _regras_validas()
    _dominios(dados)["tlds_abusados"] = ["top", "cfd"]

    with pytest.raises(ValidationError, match="cfd"):
        Regras.model_validate(dados)


def test_recusa_nome_de_marca_com_hifen_ou_maiuscula() -> None:
    """O nome é comparado com pedaços do host já separados por "-" e ".": "Itau" ou
    "banco-inter" nunca casariam, e o erro ficaria silencioso."""
    dados = _regras_validas()
    _lista(dados, "marcas")[0]["nomes"] = ["banco-inter"]

    with pytest.raises(ValidationError, match="banco-inter"):
        Regras.model_validate(dados)


def test_frases_do_bloco_de_links_so_usam_a_marca() -> None:
    """O que a tela escreve ao lado do domínio também é template, e também sem {dominio}: o
    domínio já está ao lado, como texto, e não precisa entrar na frase."""
    dominios = carregar_regras().dominios
    modelos = [s.no_link for s in dominios.sinais] + [
        dominios.link_oficial,
        dominios.link_sem_sinal,
    ]

    for modelo in modelos:
        assert modelo.placeholders <= {"marca"}


def test_conselhos_do_bloco_de_links_sao_frases_fixas_e_diferentes() -> None:
    """Item 12 da fatia 9: frase do oficial diferente da do golpe, e nenhuma com placeholder."""
    dominios = carregar_regras().dominios
    assert dominios.link_conselho != dominios.link_conselho_oficial
    for frase in (dominios.link_conselho, dominios.link_conselho_oficial):
        assert "{" not in frase
