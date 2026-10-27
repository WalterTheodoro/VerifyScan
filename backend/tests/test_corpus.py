"""O corpus rotulado (`corpus/casos/`) — formato, dado pessoal e repetição (ADR-0006, ADR-0021).

Este é o guard que o `tools/pii.py` anunciava: ele varre cada caso antes de o commit chegar ao
histórico, onde `git rm` não desfaz. Lê o YAML cru, sem passar pelo carregador do
`avaliar_corpus`, para não depender do código que ele protege.

Quando acusa dado pessoal, o teste diz o tipo e a posição, nunca o valor: o log do CI não pode
virar o lugar onde o dado vaza.
"""

from datetime import date
from pathlib import Path
from typing import Any

import yaml

from app.analyzers.normalizacao import normalizar
from tools.pii import VALOR_MONETARIO, varrer

PASTA = Path(__file__).resolve().parents[2] / "corpus" / "casos"

OBRIGATORIOS = {
    "id",
    "conteudo",
    "rotulo",
    "fonte",
    "autor",
    "canal",
    "divisao",
    "data",
    "observacoes",
}
OPCIONAIS = {"padrao", "grupo"}
VALORES = {
    "rotulo": {"golpe", "legitimo"},
    "autor": {"claude", "walter"},
    "canal": {"sms", "whatsapp", "email", "notificacao", "print"},
    "divisao": {"calibracao", "teste"},
}

# Plano de execução, Fase 2: no mínimo 150 casos, ao menos 60 legítimos.
MINIMO_DE_CASOS = 150
MINIMO_DE_LEGITIMOS = 60


def _ler_casos() -> list[tuple[str, dict[str, Any]]]:
    casos = []
    for arquivo in sorted(PASTA.glob("*.yaml")):
        with arquivo.open(encoding="utf-8") as aberto:
            casos.append((arquivo.name, yaml.safe_load(aberto)))
    return casos


CASOS = _ler_casos()


def test_corpus_tem_o_tamanho_minimo_da_fase_2() -> None:
    legitimos = sum(1 for _, caso in CASOS if caso.get("rotulo") == "legitimo")

    assert len(CASOS) >= MINIMO_DE_CASOS
    assert legitimos >= MINIMO_DE_LEGITIMOS


def test_todo_caso_segue_o_formato() -> None:
    problemas = []
    for nome, caso in CASOS:
        if not isinstance(caso, dict):
            problemas.append(f"{nome}: não é um mapeamento YAML")
            continue
        if faltando := OBRIGATORIOS - caso.keys():
            problemas.append(f"{nome}: faltam {sorted(faltando)}")
        if sobrando := caso.keys() - OBRIGATORIOS - OPCIONAIS:
            problemas.append(f"{nome}: campos desconhecidos {sorted(sobrando)}")
        for campo, permitidos in VALORES.items():
            if campo in caso and caso[campo] not in permitidos:
                problemas.append(f"{nome}: {campo} fora de {sorted(permitidos)}")
        # Sem aspas, `id: 0001` vira o inteiro 1 e o vínculo com o arquivo se perde.
        if not isinstance(caso.get("id"), str) or not nome.startswith(f"{caso.get('id')}-"):
            problemas.append(f"{nome}: id precisa ser texto e abrir o nome do arquivo")
        if not isinstance(caso.get("conteudo"), str) or not caso["conteudo"].strip():
            problemas.append(f"{nome}: conteudo vazio")
        if not isinstance(caso.get("data"), date):
            problemas.append(f"{nome}: data precisa ser AAAA-MM-DD")

    assert problemas == []


def test_nenhum_caso_tem_dado_pessoal() -> None:
    """CPF, telefone e e-mail barram sempre. Valor em reais só passa em caso sintético: ali ele
    foi inventado, e trocá-lo por placeholder tiraria da IA a pista do valor (ADR-0021)."""
    problemas = []
    for nome, caso in CASOS:
        sintetico = caso.get("fonte") == "sintetico"
        for campo in ("conteudo", "observacoes", "padrao"):
            for achado in varrer(str(caso.get(campo) or "")):
                if achado.tipo == VALOR_MONETARIO and sintetico:
                    continue
                problemas.append(f"{nome}: {achado.tipo} em {campo}, posição {achado.inicio}")

    assert problemas == []


def test_nenhuma_mensagem_se_repete() -> None:
    """Comparado depois de normalizar: mudar acento, caixa ou espaço não faz um caso novo."""
    vistos: dict[str, str] = {}
    repetidos = []
    for nome, caso in CASOS:
        chave = normalizar(str(caso.get("conteudo", "")))
        if chave in vistos:
            repetidos.append(f"{nome} repete {vistos[chave]}")
        vistos.setdefault(chave, nome)

    assert repetidos == []


def test_um_grupo_fica_inteiro_numa_divisao() -> None:
    """Quase-duplicatas dividem um grupo; calibrar num e testar no gêmeo inflaria o teste."""
    divisoes: dict[str, set[str]] = {}
    for _, caso in CASOS:
        if grupo := caso.get("grupo"):
            divisoes.setdefault(grupo, set()).add(caso.get("divisao", ""))

    assert {grupo: lados for grupo, lados in divisoes.items() if len(lados) > 1} == {}
