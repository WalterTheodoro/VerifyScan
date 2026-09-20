"""Guard de PII do corpus — varre arquivos com `tools.pii.varrer` e falha se achar algo.

Uso, a partir de `backend/`:

    uv run python -m tools.guard_corpus              # varre corpus/casos/
    uv run python -m tools.guard_corpus a.yaml dir/  # varre só o que for passado

Códigos de saída:
    0 — tudo foi lido e nada foi encontrado;
    1 — há pelo menos um achado (mesmo que algo mais não tenha podido ser lido);
    2 — nada foi achado, mas algo não pôde ser verificado (caminho inexistente, arquivo
        ilegível).

O 2 existe porque o guard falha fechado: "não consegui ler" não pode sair como "está limpo".
Um caminho errado no workflow que devolvesse 0 deixaria o CI verde para sempre.

Tudo vai para stderr, e o valor achado sai mascarado — o log do CI é público, e imprimir o
PII inteiro ali publicaria justamente o que o guard existe para barrar.
"""

import argparse
import sys
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

from tools.pii import varrer

# backend/tools/guard_corpus.py → raiz do repositório, para o padrão não depender do cwd.
CORPUS_PADRAO = Path(__file__).resolve().parents[2] / "corpus" / "casos"

VISIVEIS = 2  # quantos caracteres alfanuméricos do fim do valor ficam à mostra


def mascarar(valor: str) -> str:
    """Troca por "*" todo caractere alfanumérico menos os últimos, e mantém a pontuação.

    "123.456.789-09" vira "***.***.***-09": dá para reconhecer o tipo e achar o trecho no
    arquivo, mas não para reconstruir o dado.
    """
    total = sum(caractere.isalnum() for caractere in valor)
    mascarado = []
    vistos = 0
    for caractere in valor:
        if caractere.isalnum():
            vistos += 1
            if vistos <= total - VISIVEIS:
                caractere = "*"
        mascarado.append(caractere)
    return "".join(mascarado)


def linha_e_coluna(texto: str, posicao: int) -> tuple[int, int]:
    """Converte a posição no texto em linha e coluna, ambas contadas a partir de 1."""
    linha = texto.count("\n", 0, posicao) + 1
    inicio_da_linha = texto.rfind("\n", 0, posicao) + 1
    return linha, posicao - inicio_da_linha + 1


def arquivos(caminho: Path) -> Iterator[Path]:
    """Devolve o próprio arquivo, ou todos os arquivos sob o diretório, em ordem estável."""
    if caminho.is_file():
        yield caminho
    else:
        yield from sorted(item for item in caminho.rglob("*") if item.is_file())


def ler_texto(arquivo: Path) -> str | None:
    """Lê o arquivo como UTF-8. Devolve None se for binário; levanta erro se for ilegível."""
    conteudo = arquivo.read_bytes()
    # Byte nulo não aparece em texto: é a heurística do Git para reconhecer binário.
    if b"\x00" in conteudo:
        return None
    return conteudo.decode("utf-8")


def erro(mensagem: str) -> None:
    print(f"guard_corpus: {mensagem}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="guard_corpus",
        description="Procura dados pessoais (CPF, telefone, e-mail, valor) em arquivos de texto.",
    )
    parser.add_argument(
        "caminhos",
        nargs="*",
        type=Path,
        default=[CORPUS_PADRAO],
        help="arquivos ou diretórios a varrer (padrão: corpus/casos/)",
    )
    argumentos = parser.parse_args(argv)

    contagem: Counter[str] = Counter()
    houve_erro = False

    for caminho in argumentos.caminhos:
        if not caminho.exists():
            erro(f"{caminho}: caminho não encontrado")
            houve_erro = True
            continue
        for arquivo in arquivos(caminho):
            try:
                texto = ler_texto(arquivo)
            except (OSError, UnicodeDecodeError) as excecao:
                erro(f"{arquivo}: não foi possível ler como UTF-8 ({excecao.__class__.__name__})")
                houve_erro = True
                continue
            if texto is None:
                continue
            for achado in varrer(texto):
                linha, coluna = linha_e_coluna(texto, achado.inicio)
                print(
                    f"{arquivo}:{linha}:{coluna}: {achado.tipo}: {mascarar(achado.valor)}",
                    file=sys.stderr,
                )
                contagem[achado.tipo] += 1

    if contagem:
        por_tipo = ", ".join(f"{tipo}: {total}" for tipo, total in sorted(contagem.items()))
        erro(f"{contagem.total()} achado(s) de PII — {por_tipo}")
    elif not houve_erro:
        erro("nenhum achado de PII")

    if contagem:
        return 1
    return 2 if houve_erro else 0


if __name__ == "__main__":
    raise SystemExit(main())
