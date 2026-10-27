"""Sorteia a divisão de cada caso do corpus entre `calibracao` e `teste` — uma vez só (ADR-0021).

    cd backend
    uv run python -m tools.sortear_divisao

Regra que sustenta o número do relatório: ajuste de peso, padrão ou prompt olha só a calibração;
o teste só serve para relatar. Para isso a divisão não pode ser refeita depois de ver resultado.
Por isso este script só escreve `divisao:` em caso que ainda não tem, e nunca altera uma divisão
existente. Rodar de novo sem caso novo não muda nenhum arquivo.

O sorteio é estratificado por rótulo (30% de cada um vai para o teste) e respeita o `grupo`: as
quase-duplicatas caem inteiras do mesmo lado, senão calibrar num caso e testar no gêmeo inflaria
o teste. Caso novo de um grupo que já tem lado segue esse lado.
"""

import random
import sys
from pathlib import Path
from typing import Any

import yaml

PASTA_CASOS = Path(__file__).resolve().parents[2] / "corpus" / "casos"

# A semente vai para o carimbo de todo relatório do `avaliar_corpus`.
SEMENTE = 20261027
FRACAO_TESTE = 0.3


def sortear(casos: list[dict[str, Any]], semente: int = SEMENTE) -> dict[str, str]:
    """Devolve `{id: divisao}` só para os casos que ainda não têm divisão."""
    lado_do_grupo = {
        caso["grupo"]: caso["divisao"] for caso in casos if caso.get("grupo") and "divisao" in caso
    }
    resultado: dict[str, str] = {}
    pendentes = []
    for caso in casos:
        if "divisao" in caso:
            continue
        if caso.get("grupo") in lado_do_grupo:
            resultado[caso["id"]] = lado_do_grupo[caso["grupo"]]
        else:
            pendentes.append(caso)

    gerador = random.Random(semente)
    for rotulo in sorted({caso["rotulo"] for caso in pendentes}):
        # Unidade de sorteio: o grupo inteiro, ou o caso sozinho quando não tem grupo.
        unidades: dict[str, list[str]] = {}
        for caso in pendentes:
            if caso["rotulo"] == rotulo:
                unidades.setdefault(caso.get("grupo") or caso["id"], []).append(caso["id"])
        # Ordena antes de embaralhar: a ordem de leitura dos arquivos não pode mudar o sorteio.
        ordem = sorted(unidades)
        gerador.shuffle(ordem)

        alvo = round(FRACAO_TESTE * sum(len(ids) for ids in unidades.values()))
        no_teste = 0
        for chave in ordem:
            ids = unidades[chave]
            lado = "teste" if no_teste + len(ids) <= alvo else "calibracao"
            if lado == "teste":
                no_teste += len(ids)
            resultado.update(dict.fromkeys(ids, lado))
    return resultado


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    arquivos = sorted(PASTA_CASOS.glob("*.yaml"))
    casos = []
    caminho_do_id = {}
    for arquivo in arquivos:
        with arquivo.open(encoding="utf-8") as aberto:
            caso = yaml.safe_load(aberto)
        casos.append(caso)
        caminho_do_id[caso["id"]] = arquivo

    divisao = sortear(casos)
    # Acrescenta a linha no fim em vez de reescrever o YAML: o resto do arquivo fica como foi
    # escrito, e o diff mostra só a divisão.
    for id_caso, lado in divisao.items():
        with caminho_do_id[id_caso].open("a", encoding="utf-8", newline="\n") as aberto:
            aberto.write(f"divisao: {lado}\n")

    print(f"Semente {SEMENTE}: {len(divisao)} caso(s) novo(s) dividido(s).")
    for lado in ("calibracao", "teste"):
        print(f"  {lado}: {sum(1 for valor in divisao.values() if valor == lado)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
