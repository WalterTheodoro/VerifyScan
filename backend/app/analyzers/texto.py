"""TextAnalyzer — padrões linguísticos de golpe no texto (§5.4.1 do RFC).

Analisador puro: entra uma string, sai `list[Fator]`. Sem I/O, sem banco, sem rede — é isso
que o torna testável e mensurável contra o corpus na Fase 2.

O nome da classe segue o RFC (`TextAnalyzer`), não a convenção de português do CLAUDE.md §6:
todo o documento, os ADRs e o diário se referem a ele por esse nome, e rastreabilidade com a
especificação vale mais que uniformidade de idioma aqui.
"""

from app.analyzers.normalizacao import normalizar
from app.schemas.analise import Fator
from app.scoring.regras import Regras


class TextAnalyzer:
    """Aplica os padrões do `regras.yaml` e devolve um fator por categoria que casar."""

    def __init__(self, regras: Regras) -> None:
        self._categorias = regras.categorias

    def analisar(self, texto: str) -> list[Fator]:
        """Um fator por categoria, no máximo — quantos padrões dela casaram não importa.

        A categoria pontuar uma vez só é a regra de agregação do ADR-0004. O `ScoringEngine`
        a reaplica sobre o conjunto completo de fatores; aqui ela sai de graça, porque o laço
        é por categoria.
        """
        normalizado = normalizar(texto)
        return [
            Fator(
                tipo="texto",
                categoria=categoria.id,
                descricao=categoria.descricao.renderizar(),
                peso=categoria.peso,
            )
            for categoria in self._categorias
            if any(padrao.search(normalizado) for padrao in categoria.padroes)
        ]
