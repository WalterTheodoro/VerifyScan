"""DomainAnalyzer — sinais léxicos sobre os links da mensagem (Fase 3, ADR-0022).

Analisador puro: entram as URLs que o `URLExtractor` já extraiu, sai `list[Fator]`. Sem I/O, sem
banco, sem rede. E, mais que isso, **nunca abre o link**: nem GET, nem HEAD, nem consulta DNS, nem
segue redirecionamento. Abrir o link pode avisar o golpista de que a vítima clicou, baixar
conteúdo malicioso para o servidor ou servir de SSRF. Tudo aqui é sobre o texto do endereço.

O domínio registrável (eTLD+1) sai da Public Suffix List embutida no pacote `publicsuffixlist`,
que não baixa nada em tempo de execução. Sem ela, `golpe.com.br` e `bradesco.com.br` teriam o
mesmo "domínio" (`com.br`), e dividir por ponto erraria todo `.com.br`.

O nome da classe segue o RFC (`DomainAnalyzer`), como o `TextAnalyzer`.
"""

import ipaddress
import re
import unicodedata
from collections.abc import Iterable
from urllib.parse import urlsplit

from publicsuffixlist import PublicSuffixList
from pydantic import BaseModel, ConfigDict

from app.analyzers.urls import URLExtraida
from app.schemas.analise import CategoriaFator, Fator, LinkDaMensagem
from app.scoring.descricoes import ValoresDescricao
from app.scoring.regras import ConfiguracaoDominios, Regras

# Host que é número: decimal com ponto (1.2.3.4), inteiro (16909060) ou hexadecimal (0x7f.1).
# Navegador aceita as três formas, e golpe usa as duas últimas para não parecer IP.
_HOST_NUMERICO = re.compile(r"(0x[0-9a-f]+|\d+)(\.(0x[0-9a-f]+|\d+)){0,3}")

# Dígito no lugar de letra: "bradesc0", "regu1ariza". Só os dois mais comuns, de propósito.
_DIGITO_COMO_LETRA = str.maketrans("01", "ol")


class Achado(BaseModel):
    """Um sinal encontrado num link. `marca` só nos sinais de marca e de imitação."""

    model_config = ConfigDict(frozen=True)

    categoria: CategoriaFator
    marca: str | None = None


class AvaliacaoLink(BaseModel):
    """O que o analisador concluiu de um link: o domínio registrável, de quem ele é oficial (se
    for) e os sinais. É o que a tela mostra no lugar do link inteiro."""

    model_config = ConfigDict(frozen=True)

    dominio: str
    oficial_de: str | None = None
    sinais: tuple[Achado, ...] = ()


class DomainAnalyzer:
    def __init__(self, regras: Regras) -> None:
        self._config: ConfiguracaoDominios = regras.dominios
        # A lista que vem dentro do pacote; nada é baixado (ADR-0022).
        self._psl = PublicSuffixList()

    def analisar(self, urls: Iterable[URLExtraida]) -> list[Fator]:
        """Um fator por categoria, no máximo, na ordem em que apareceu (ADR-0004)."""
        fatores: dict[CategoriaFator, Fator] = {}
        for url in urls:
            for achado in self.avaliar(url).sinais:
                if achado.categoria not in fatores:
                    fatores[achado.categoria] = self._fator(achado)
        return list(fatores.values())

    def descrever(self, urls: Iterable[URLExtraida]) -> list[LinkDaMensagem]:
        """O bloco de links da tela: um item por domínio registrável, na ordem de aparição, com
        as frases do `regras.yaml`. Dois links do mesmo domínio somam o que se achou nos dois."""
        por_dominio: dict[str, list[AvaliacaoLink]] = {}
        for url in urls:
            avaliacao = self.avaliar(url)
            por_dominio.setdefault(avaliacao.dominio, []).append(avaliacao)
        return [
            LinkDaMensagem(dominio=dominio, observacoes=self._observacoes(avaliacoes))
            for dominio, avaliacoes in por_dominio.items()
        ]

    def avaliar(self, url: URLExtraida) -> AvaliacaoLink:
        host = url.host
        numerico = _e_numerico(host)
        dominio = host if numerico else (self._psl.privatesuffix(host) or host)

        oficial = None if numerico else self._oficial_de(host)
        if oficial is not None:
            # Domínio oficial não pontua: é informação para a IA, e o nível do motor segue sendo
            # o que o resto da mensagem der (regra do maior, ADR-0020).
            return AvaliacaoLink(dominio=dominio, oficial_de=oficial)

        achados: list[Achado] = []
        if numerico:
            achados.append(Achado(categoria="link_ip"))
        else:
            if _tem_caractere_enganoso(host):
                achados.append(Achado(categoria="link_caracteres_enganosos"))
            marca = self._marca(host, dominio)
            if marca is not None:
                achados.append(marca)
            if dominio in self._config.encurtadores:
                achados.append(Achado(categoria="link_encurtado"))
            if host.rsplit(".", 1)[-1] in self._config.tlds_abusados:
                achados.append(Achado(categoria="link_tld_abusado"))
        if self._tem_isca(url):
            achados.append(Achado(categoria="link_palavra_isca"))
        # O extrator completa "gov.br" com `http://`: só conta o que a pessoa de fato recebeu.
        if url.original.lower().startswith("http://"):
            achados.append(Achado(categoria="link_sem_https"))
        if self._tem_truque(url, host, dominio, numerico):
            achados.append(Achado(categoria="link_truque_endereco"))
        return AvaliacaoLink(dominio=dominio, sinais=tuple(achados))

    # ── sinais ───────────────────────────────────────────────────────────────────────────────

    def _oficial_de(self, host: str) -> str | None:
        """A marca dona do domínio, pelo oficial mais específico: `caixa.gov.br` é da Caixa, e
        `www.gov.br` é do gov.br, que vem antes das outras marcas sob gov.br na lista."""
        melhor: tuple[int, str] | None = None
        for marca in self._config.marcas:
            for oficial in marca.oficiais:
                cobre = host == oficial or host.endswith("." + oficial)
                if cobre and (melhor is None or len(oficial) > melhor[0]):
                    melhor = (len(oficial), marca.nome)
        return melhor[1] if melhor else None

    def _marca(self, host: str, dominio: str) -> Achado | None:
        """Nome inteiro da marca em qualquer parte do host → marca fora do oficial. Senão, nome
        parecido no rótulo do domínio registrável → imitação (ADR-0004 §3: a distância de
        edição só olha esse rótulo, não o host inteiro)."""
        sufixo = self._psl.publicsuffix(host) or ""
        antes_do_sufixo = host.removesuffix(sufixo).rstrip(".")
        if not antes_do_sufixo:
            return None
        rotulos = antes_do_sufixo.split(".")

        for peca in _pecas(rotulos):
            for marca in self._config.marcas:
                if peca in marca.nomes:
                    return Achado(categoria="link_marca_nao_oficial", marca=marca.nome)

        # Só o rótulo do registrável: em `login.bradesc0.example`, "bradesc0", não "login".
        registravel = dominio.removesuffix(sufixo).rstrip(".")
        for peca in _pecas([registravel]):
            comparavel = _comparavel(peca)
            for marca in self._config.marcas:
                for nome in marca.nomes:
                    # "bradesc0" e "nubánk" viram o nome exato só depois de normalizar.
                    if comparavel == nome:
                        return Achado(categoria="link_parecido_com_oficial", marca=marca.nome)
                    limite = self._config.semelhanca.limite(nome) if marca.semelhanca else 0
                    if 0 < _distancia(comparavel, nome) <= limite:
                        return Achado(categoria="link_parecido_com_oficial", marca=marca.nome)
        return None

    def _tem_isca(self, url: URLExtraida) -> bool:
        """No host e no caminho; a query fica de fora, porque é onde moram `utm_*` e afins."""
        caminho = urlsplit(url.canonica).path
        alvo = _comparavel(_decodificar(url.host) + caminho)
        return any(isca in alvo for isca in self._config.palavras_isca)

    def _tem_truque(self, url: URLExtraida, host: str, dominio: str, numerico: bool) -> bool:
        original = url.original if "://" in url.original else f"http://{url.original}"
        partes = urlsplit(original)
        # `https://bradesco.com.br@golpe.example`: o que vem antes do "@" não é o site.
        if partes.username is not None:
            return True
        try:
            porta = partes.port
        except ValueError:
            porta = None
        if porta is not None and porta not in self._config.portas_comuns:
            return True
        if numerico:
            return False
        subdominios = [r for r in host.removesuffix(dominio).rstrip(".").split(".") if r]
        if subdominios[:1] == ["www"]:
            subdominios = subdominios[1:]
        return len(subdominios) >= self._config.subdominios_suspeitos_a_partir_de

    def _fator(self, achado: Achado) -> Fator:
        sinal = self._config.sinal(achado.categoria)
        return Fator(
            tipo="dominio",
            categoria=achado.categoria,
            descricao=sinal.descricao.renderizar(_valores(achado.marca)),
            peso=sinal.peso,
        )

    def _observacoes(self, avaliacoes: list[AvaliacaoLink]) -> list[str]:
        """Sem repetir frase. O oficial só aparece quando nenhum link do domínio teve sinal: os
        dois juntos não acontecem, porque domínio oficial não dispara sinal nenhum."""
        frases: list[str] = []
        for avaliacao in avaliacoes:
            for achado in avaliacao.sinais:
                sinal = self._config.sinal(achado.categoria)
                frase = sinal.no_link.renderizar(_valores(achado.marca))
                if frase not in frases:
                    frases.append(frase)
        if frases:
            return frases
        oficial = avaliacoes[0].oficial_de
        if oficial is not None:
            return [self._config.link_oficial.renderizar(_valores(oficial))]
        return [self._config.link_sem_sinal.renderizar()]


# ── funções puras ────────────────────────────────────────────────────────────────────────────


def _valores(marca: str | None) -> ValoresDescricao:
    return ValoresDescricao(marca=marca) if marca else ValoresDescricao()


def _e_numerico(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return _HOST_NUMERICO.fullmatch(host) is not None
    return True


def _tem_caractere_enganoso(host: str) -> bool:
    """Punycode, letra de fora do ASCII (o "a" cirílico, U+0430) ou caractere invisível.

    Também dispara em domínio acentuado legítimo (`açaí.com.br`): é raro em SMS e WhatsApp, e
    distinguir um do outro pediria a tabela de "confusáveis" do Unicode. Limitação no ADR-0022.
    """
    return not host.isascii() or any(rotulo.startswith("xn--") for rotulo in host.split("."))


def _decodificar(rotulos: str) -> str:
    """`xn--nubnk-sqa` → `nubánk`. Punycode inválido fica como está."""
    try:
        return rotulos.encode("ascii").decode("idna")
    except UnicodeError:
        return rotulos


def _pecas(rotulos: list[str]) -> list[str]:
    """Cada rótulo, já decodificado, em pedaços separados por "-", mais o rótulo inteiro sem os
    hífens: `banco-do-brasil` dá "banco", "do", "brasil" e "bancodobrasil"."""
    pecas: list[str] = []
    for rotulo in rotulos:
        decodificado = _decodificar(rotulo)
        pecas.extend(peca for peca in decodificado.split("-") if peca)
        pecas.append(decodificado.replace("-", ""))
    return pecas


def _comparavel(texto: str) -> str:
    """Sem acento, sem caractere invisível e com 0→o e 1→l: a forma que o olho lê."""
    decomposto = unicodedata.normalize("NFKD", texto.lower())
    visivel = "".join(
        c for c in decomposto if not unicodedata.combining(c) and unicodedata.category(c) != "Cf"
    )
    return visivel.translate(_DIGITO_COMO_LETRA)


def _distancia(a: str, b: str) -> int:
    """Distância de Levenshtein: quantas letras inseridas, removidas ou trocadas levam a em b.

    A biblioteca padrão não tem; a versão clássica por programação dinâmica, uma linha por vez.
    """
    anterior = list(range(len(b) + 1))
    for i, letra_a in enumerate(a, start=1):
        atual = [i]
        for j, letra_b in enumerate(b, start=1):
            atual.append(
                min(
                    anterior[j] + 1,  # remove
                    atual[j - 1] + 1,  # insere
                    anterior[j - 1] + (letra_a != letra_b),  # troca
                )
            )
        anterior = atual
    return anterior[-1]
