"""Serviço de análise — orquestra o pipeline da Fase 1 e valida a entrada do usuário.

A regra de negócio mora aqui, não na rota (CLAUDE.md §6). Nesta fase o pipeline é curto e
síncrono: extrai links, aplica as heurísticas de texto, agrega. Nada disso faz I/O, então não
há o que aguardar — o `await` real chega na Fase 4, com RDAP e reputação em paralelo.
"""

from app.analyzers.normalizacao import normalizar
from app.analyzers.texto import TextAnalyzer
from app.analyzers.urls import URLExtractor
from app.schemas.analise import RespostaAnalise
from app.scoring.motor import ScoringEngine


class EntradaInvalida(Exception):
    """Conteúdo que o sistema não tem como analisar. A mensagem é exibida ao usuário.

    Por isso ela é escrita em pt-BR, sem jargão, e diz o que fazer — não é log de
    desenvolvedor (regra de negócio da §2.5 do RFC).
    """


class ServicoAnalise:
    def __init__(
        self,
        analisador: TextAnalyzer,
        extrator: URLExtractor,
        motor: ScoringEngine,
        maximo_de_caracteres: int,
    ) -> None:
        self._analisador = analisador
        self._extrator = extrator
        self._motor = motor
        self._maximo_de_caracteres = maximo_de_caracteres

    def analisar(self, texto: str) -> RespostaAnalise:
        self._validar(texto)
        urls = self._extrator.extrair(texto)
        resultado = self._motor.pontuar(self._analisador.analisar(texto))
        return RespostaAnalise(
            score=resultado.score,
            nivel_risco=resultado.nivel_risco,
            fatores=resultado.fatores,
            urls_analisadas=[url.canonica for url in urls],
        )

    def _validar(self, texto: str) -> None:
        """Recusa, nunca trunca.

        Analisar os primeiros N caracteres de uma mensagem longa devolveria um nível de risco
        calculado sobre conteúdo parcial: um pedido de PIX no fim da mensagem sumiria e a
        resposta viria BAIXO. Recusar é honesto; truncar em silêncio produz falso negativo.
        """
        if len(texto) > self._maximo_de_caracteres:
            raise EntradaInvalida(
                f"A mensagem tem {len(texto)} caracteres e o limite é "
                f"{self._maximo_de_caracteres}. Envie só o trecho mais importante — "
                "normalmente a parte com o pedido ou com o link."
            )
        if not any(caractere.isalnum() for caractere in normalizar(texto)):
            raise EntradaInvalida(
                "Não encontramos texto para analisar. Cole a mensagem suspeita e tente de novo."
            )
