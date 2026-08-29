"""`scoring/regras.yaml` — carregamento, validação e o mecanismo de template das descrições.

Este arquivo é o guarda da invariante 5 do CLAUDE.md: peso e padrão são dado versionado, não
número mágico em `.py`. Os pesos conferidos aqui vêm da §5.4.1 do RFC (p. 22-23).
"""

import re

import pytest
from pydantic import ValidationError

from app.scoring.descricoes import PLACEHOLDERS_PERMITIDOS, ModeloDescricao
from app.scoring.regras import Regras, carregar_regras

# §5.4.1 do RFC, tabela "Categoria / Exemplos de padrões detectados / Peso".
PESOS_DO_RFC = {
    "urgencia": 10,
    "personificacao_marca": 15,
    "ameaca_bloqueio": 15,
    "premio_falso": 20,
    "solicitacao_financeira": 25,
    "dados_pessoais": 25,
}


def test_regras_carregam_do_yaml() -> None:
    regras = carregar_regras()

    assert regras.versao >= 1
    assert regras.agregacao == "por_categoria"


def test_as_seis_categorias_existem_com_os_pesos_do_rfc() -> None:
    """§5.4.1 tem seis categorias; a §5.4.7 funde duas delas — e está errada (errata, item 3)."""
    regras = carregar_regras()

    assert {categoria.id: categoria.peso for categoria in regras.categorias} == PESOS_DO_RFC


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
        for id_, peso in PESOS_DO_RFC.items()
    ]
    return {
        "versao": 1,
        "agregacao": "por_categoria",
        "faixas": {"baixo_ate": 30, "medio_ate": 60},
        "categorias": categorias,
    }


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

    with pytest.raises(ValidationError, match="dados_pessoais"):
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
