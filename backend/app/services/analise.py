"""Serviço de análise — orquestra o pipeline da Fase 1 e valida a entrada do usuário.

A regra de negócio mora aqui, não na rota (CLAUDE.md §6). O pipeline é curto e síncrono: extrai
links, aplica as heurísticas de texto e as de link (que nunca abrem o link, ADR-0022), agrega.
Nada disso faz I/O, então não há o que aguardar — o `await` real chega na Fase 4, com RDAP e
reputação em paralelo.

O que este serviço devolve é a resposta **sem IA**: o nível do motor com a orientação fixa do
nível (o plano B do ADR-0020). A IA entra depois, no orquestrador, e só pode subir o nível.
"""

import re

from app.analyzers.dominios import DomainAnalyzer
from app.analyzers.normalizacao import normalizar
from app.analyzers.texto import TextAnalyzer
from app.analyzers.urls import URLExtractor, URLExtraida
from app.formulator.limpeza import PADRAO_EMAIL, PADRAO_ESQUEMA, PADRAO_TELEFONE
from app.ocr.leitura import textos_recebidos, trocar_nas_mensagens
from app.schemas.analise import LinkDaMensagem, RespostaAnalise, TipoInput
from app.scoring.motor import ScoringEngine
from app.scoring.respostas import RespostasPadrao

# Lugar provisório de cada link enquanto o texto é trocado: sem ponto, para o extrator não o achar
# de novo, e sem dígitos em volta que o padrão de telefone junte. Caracteres de uso privado, que
# nenhuma mensagem real tem — e que, por garantia, saem do texto antes.
_ABRE, _FECHA = "\ue000", "\ue001"
_PROVISORIO = re.compile(f"{_ABRE}(\\d+){_FECHA}")

# Hífen que não quebra (U+2011): em 390 px, "[e-mail]" quebrava em "[e-" / "mail]".
EMAIL_NA_TELA = "[e\u2011mail]"


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
        dominios: DomainAnalyzer,
        motor: ScoringEngine,
        respostas: RespostasPadrao,
        maximo_de_caracteres: int,
    ) -> None:
        self._analisador = analisador
        self._extrator = extrator
        self._dominios = dominios
        self._motor = motor
        self._respostas = respostas
        self._maximo_de_caracteres = maximo_de_caracteres

    def analisar(self, texto: str) -> RespostaAnalise:
        self._validar(texto)
        urls = self._extrator.extrair(texto)
        fatores = self._analisador.analisar(texto) + self._dominios.analisar(urls)
        resultado = self._motor.pontuar(fatores)
        return RespostaAnalise(
            score=resultado.score,
            nivel_risco=resultado.nivel_risco,
            fatores=resultado.fatores,
            links=self._dominios.descrever(urls),
            nivel_motor=resultado.nivel_risco,
            orientacao=self._respostas.para(resultado.nivel_risco),
            explicacao_indisponivel=True,
        )

    def links_do_texto(
        self, texto: str | None, tipo_input: TipoInput = "texto"
    ) -> list[LinkDaMensagem]:
        """O bloco de links de uma mensagem já analisada: o histórico guarda o texto, não os
        links (ADR-0009), e os recalcula daqui, com as regras de hoje. Sem texto, sem links.

        Num print, só do que a pessoa recebeu, como na análise (ADR-0023): o link que ela mesma
        mandou não é o da mensagem suspeita."""
        if texto is None:
            return []
        recebido = textos_recebidos(texto) if tipo_input == "imagem" else texto
        return self._dominios.descrever(self._extrator.extrair(recebido))

    def para_exibir(self, texto: str) -> str:
        """A transcrição do print como a tela mostra (correção 9.1): cada link vira
        "[link: domínio registrável]", o mesmo do bloco de links; cada telefone, "[telefone]";
        cada e-mail, "[e-mail]" com hífen que não quebra (U+2011). Link de outro esquema (`intent://`,
        `ftp://`) também sai: com o domínio, se houver; sem, "[link]".

        Dentro da imagem o link não é clicável nem fácil de copiar; transcrito, viraria texto
        pronto para copiar — um atalho que o print não tinha. O texto guardado e o que o motor
        analisa continuam completos: a troca é só na exibição, e só aqui.

        A ordem importa: o e-mail sai antes (o domínio dele pareceria um link) e o telefone
        depois dos links (um wa.me/55119… é um link só). O extrator para em
        `maximo_por_analise`; por isso as voltas, até não sobrar link.
        """
        exibido = PADRAO_EMAIL.sub(EMAIL_NA_TELA, texto.replace(_ABRE, "").replace(_FECHA, ""))
        dominios: list[str] = []

        def provisorio(url: URLExtraida) -> str:
            dominios.append(self._dominios.avaliar(url).dominio)
            return f"{_ABRE}{len(dominios) - 1}{_FECHA}"

        def outro_esquema(casamento: re.Match[str]) -> str:
            # http e https ficam para o extrator, que tira a pontuação do fim da frase.
            if casamento.group().lower().startswith(("http://", "https://")):
                return casamento.group()
            achados = self._extrator.extrair(casamento.group())
            return provisorio(achados[0]) if achados else "[link]"

        exibido = PADRAO_ESQUEMA.sub(outro_esquema, exibido)
        provisorio_de: dict[str, str] = {}
        while urls := self._extrator.extrair(exibido):
            for url in urls:
                provisorio_de[url.original] = provisorio(url)
            # Uma passada só, do original mais longo para o mais curto: `bit.ly/x` não pode ser
            # trocado pela metade porque `bit.ly` também foi achado.
            originais = sorted({url.original for url in urls}, key=len, reverse=True)
            padrao = "|".join(map(re.escape, originais))
            trocado = re.sub(padrao, lambda c: provisorio_de[c.group()], exibido)
            if trocado == exibido:
                break
            exibido = trocado
        exibido = PADRAO_TELEFONE.sub("[telefone]", exibido)
        return _PROVISORIO.sub(lambda c: f"[link: {dominios[int(c.group(1))]}]", exibido)

    def texto_para_exibir(self, texto: str | None, tipo_input: TipoInput) -> str | None:
        """A transcrição guardada de um print, para o histórico mostrar como a home. No texto
        colado, `None`: o "Você colou" é o que a própria pessoa colou e já está com ela."""
        if texto is None or tipo_input != "imagem":
            return None
        return trocar_nas_mensagens(texto, self.para_exibir)

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
