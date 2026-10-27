"""Carregamento e validação do `scoring/regras.yaml` (invariante 5 do CLAUDE.md).

Peso, padrão e faixa são dado versionado. Mudar um peso não pode exigir mudar código — e, do
outro lado, um YAML quebrado precisa derrubar o boot, não a primeira requisição do usuário.
Por isso toda a validação (categorias presentes, pesos positivos, faixas ordenadas, regex
compilando) acontece aqui, no carregamento. Ver ADR-0008.
"""

import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self, get_args

import yaml
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.analyzers.normalizacao import normalizar
from app.schemas.analise import CategoriaFator, NivelRisco
from app.scoring.descricoes import ModeloDescricao

CAMINHO_REGRAS = Path(__file__).parent / "regras.yaml"

CATEGORIAS_DE_LINK: tuple[CategoriaFator, ...] = tuple(
    categoria for categoria in get_args(CategoriaFator) if categoria.startswith("link_")
)
"""Os sinais léxicos do DomainAnalyzer (ADR-0022): pesos na seção `dominios` do `regras.yaml`."""

CATEGORIAS_DE_TEXTO: tuple[CategoriaFator, ...] = tuple(
    categoria for categoria in get_args(CategoriaFator) if categoria not in CATEGORIAS_DE_LINK
)
"""As seis da §5.4.1 mais `instrucao_ao_analisador` (ADR-0020): pesos e padrões na seção
`categorias` do `regras.yaml`."""

# `\D`, `\S`, `\W`, `\B` viram `\d`, `\s`, `\w`, `\b` ao passar pelo `.lower()` do normalizador —
# a regex continua compilando e passa a significar o oposto. Preferimos falhar no boot.
_CLASSE_MAIUSCULA = re.compile(r"\\[A-Z]")


def normalizar_padrao(padrao: object) -> object:
    """Passa o padrão pelo mesmo normalizador do texto.

    Recusa o que a normalização inverteria, em vez de normalizar e seguir em frente.
    """
    if not isinstance(padrao, str):
        return padrao
    if _CLASSE_MAIUSCULA.search(padrao):
        raise ValueError(
            f"padrão usa classe de regex maiúscula, que a normalização inverteria: {padrao!r}"
        )
    return normalizar(padrao)


PadraoNormalizado = Annotated[re.Pattern[str], BeforeValidator(normalizar_padrao)]
"""Escrito em português natural no YAML, normalizado e compilado no carregamento."""


class Faixas(BaseModel):
    """Cortes de classificação do score (§5.4.7 do RFC).

    São objeto de calibração na Fase 2 tanto quanto os pesos (ADR-0005), e o relatório de
    avaliação carimba os valores vigentes — daí eles serem dado, e não constante no código.
    """

    model_config = ConfigDict(frozen=True)

    baixo_ate: int = Field(gt=0)
    medio_ate: int = Field(gt=0)

    @model_validator(mode="after")
    def _ordenadas(self) -> Self:
        if self.baixo_ate >= self.medio_ate:
            raise ValueError(
                f"faixa de BAIXO (até {self.baixo_ate}) precisa terminar antes da de MÉDIO "
                f"(até {self.medio_ate})"
            )
        return self

    def classificar(self, score: int) -> NivelRisco:
        if score <= self.baixo_ate:
            return "BAIXO"
        if score <= self.medio_ate:
            return "MEDIO"
        return "ALTO"


class ConfiguracaoURLs(BaseModel):
    """Configuração da extração de links (§5.4.2). Não tem peso: extrair não pontua.

    `tlds_conhecidos` só governa host escrito sem protocolo. Sem essa lista, qualquer
    `palavra.palavra` viraria link — "relatorio.final", "Obrigado.Att". Com `http://`
    explícito não há ambiguidade e a lista não se aplica.
    """

    model_config = ConfigDict(frozen=True)

    maximo_por_analise: int = Field(gt=0)
    tlds_conhecidos: frozenset[str] = Field(min_length=1)

    @field_validator("tlds_conhecidos")
    @classmethod
    def _minusculos_e_sem_ponto(cls, tlds: frozenset[str]) -> frozenset[str]:
        invalidos = sorted(tld for tld in tlds if not tld.isalnum() or tld != tld.lower())
        if invalidos:
            raise ValueError(f"TLD deve ser alfanumérico e minúsculo, sem ponto: {invalidos}")
        return tlds


class CategoriaTexto(BaseModel):
    """Uma categoria de texto (§5.4.1 e ADR-0020): peso, descrição e os padrões que a disparam."""

    model_config = ConfigDict(frozen=True)

    id: CategoriaFator
    peso: int = Field(gt=0)
    descricao: ModeloDescricao
    padroes: tuple[PadraoNormalizado, ...] = Field(min_length=1)


_NOME_DE_MARCA = re.compile(r"[a-z0-9]+")


class SinalLink(BaseModel):
    """Um sinal do DomainAnalyzer (ADR-0022): peso e descrição. Quem o detecta é o código; o que
    ele procura (listas, limiares) fica no resto da seção `dominios`."""

    model_config = ConfigDict(frozen=True)

    id: CategoriaFator
    peso: int = Field(gt=0)
    descricao: ModeloDescricao
    no_link: ModeloDescricao = Field(
        description="A frase curta que a tela escreve ao lado do domínio, no bloco de links."
    )

    @field_validator("descricao", "no_link")
    @classmethod
    def _so_a_marca(cls, descricao: ModeloDescricao) -> ModeloDescricao:
        return _so_a_marca(descricao)


def _so_a_marca(modelo: ModeloDescricao) -> ModeloDescricao:
    """O fator vai para o banco também em análise anônima (ADR-0012). O nome da marca vem da lista
    fechada; o domínio viria da mensagem, e por isso fica de fora (fatia 8)."""
    proibidos = sorted(modelo.placeholders - {"marca"})
    if proibidos:
        raise ValueError(f"frase de link só pode usar {{marca}}, não {proibidos}")
    return modelo


class Marca(BaseModel):
    """Uma empresa ou órgão que golpe imita, com os nomes que o endereço usaria e os domínios
    oficiais dela. Um domínio oficial cobre os subdomínios: `gov.br` vale para `detran.sp.gov.br`.
    """

    model_config = ConfigDict(frozen=True)

    nome: str = Field(min_length=1, description="Como a tela e a descrição escrevem a marca.")
    nomes: frozenset[str] = Field(min_length=1)
    semelhanca: bool = Field(
        description=(
            "Entra na comparação por letras trocadas? Não para nome que é palavra comum "
            "(caixa, inter, receita): 'caixas' e 'intel' virariam imitação."
        )
    )
    oficiais: tuple[str, ...] = Field(min_length=1)

    @field_validator("nomes")
    @classmethod
    def _minusculos_sem_separador(cls, nomes: frozenset[str]) -> frozenset[str]:
        """O nome é comparado com pedaços do host já separados por "-" e ".": "Itau" ou
        "banco-inter" nunca casariam, e o erro seria silencioso."""
        invalidos = sorted(nome for nome in nomes if not _NOME_DE_MARCA.fullmatch(nome))
        if invalidos:
            raise ValueError(
                f"nome de marca deve ser minúsculo, sem acento e sem hífen: {invalidos}"
            )
        return nomes


class LimiaresSemelhanca(BaseModel):
    """Distância de edição tolerada (ADR-0004 §3): proporcional ao tamanho do nome da marca."""

    model_config = ConfigDict(frozen=True)

    minimo_de_letras: int = Field(gt=0, description="Nome mais curto que isto não é comparado.")
    curto_ate: int = Field(gt=0)
    distancia_curto: int = Field(ge=1)
    distancia_longo: int = Field(ge=1)

    def limite(self, nome: str) -> int:
        """Quantas letras trocadas ainda contam como imitação; 0 desliga a comparação."""
        if len(nome) < self.minimo_de_letras:
            return 0
        return self.distancia_curto if len(nome) <= self.curto_ate else self.distancia_longo


class ConfiguracaoDominios(BaseModel):
    """Seção `dominios` do `regras.yaml`: o que o DomainAnalyzer procura e quanto cada sinal pesa.

    Tudo aqui é sobre o texto do endereço. O sistema nunca abre o link (ADR-0022).
    """

    model_config = ConfigDict(frozen=True)

    sinais: tuple[SinalLink, ...]
    link_oficial: ModeloDescricao = Field(description="No bloco de links, o domínio oficial.")
    link_sem_sinal: ModeloDescricao = Field(description="No bloco de links, o link sem sinal.")
    encurtadores: frozenset[str] = Field(min_length=1)
    tlds_abusados: frozenset[str] = Field(min_length=1)
    palavras_isca: tuple[str, ...] = Field(min_length=1)
    portas_comuns: frozenset[int] = Field(min_length=1)
    subdominios_suspeitos_a_partir_de: int = Field(gt=0)
    semelhanca: LimiaresSemelhanca
    marcas: tuple[Marca, ...] = Field(min_length=1)

    @field_validator("link_oficial", "link_sem_sinal")
    @classmethod
    def _frases_so_com_a_marca(cls, modelo: ModeloDescricao) -> ModeloDescricao:
        return _so_a_marca(modelo)

    @field_validator("palavras_isca", mode="before")
    @classmethod
    def _iscas_normalizadas(cls, iscas: object) -> object:
        """Escritas com acento no YAML, comparadas com o host sem acento."""
        if isinstance(iscas, list):
            return [normalizar(isca) if isinstance(isca, str) else isca for isca in iscas]
        return iscas

    @model_validator(mode="after")
    def _sinais_completos_sem_repetir(self) -> Self:
        presentes = [sinal.id for sinal in self.sinais]
        fora = sorted(set(presentes) - set(CATEGORIAS_DE_LINK))
        if fora:
            raise ValueError(f"categoria que não é de link na seção dominios: {fora}")
        faltando = sorted(set(CATEGORIAS_DE_LINK) - set(presentes))
        if faltando:
            raise ValueError(f"sinais de link ausentes no regras.yaml: {faltando}")
        if len(presentes) != len(set(presentes)):
            raise ValueError(f"sinal de link repetido no regras.yaml: {presentes}")
        return self

    def sinal(self, categoria: CategoriaFator) -> SinalLink:
        return next(sinal for sinal in self.sinais if sinal.id == categoria)


class Regras(BaseModel):
    """O `regras.yaml` inteiro, validado."""

    model_config = ConfigDict(frozen=True)

    versao: int = Field(ge=1, description="Muda a cada recalibração; carimbada no relatório.")
    agregacao: Literal["por_categoria"]
    faixas: Faixas
    urls: ConfiguracaoURLs
    categorias: tuple[CategoriaTexto, ...]
    dominios: ConfiguracaoDominios

    @model_validator(mode="after")
    def _categorias_completas_sem_repetir(self) -> Self:
        presentes = [categoria.id for categoria in self.categorias]
        fora = sorted(set(presentes) - set(CATEGORIAS_DE_TEXTO))
        if fora:
            raise ValueError(f"categoria que não é de texto na seção categorias: {fora}")
        faltando = sorted(set(CATEGORIAS_DE_TEXTO) - set(presentes))
        if faltando:
            raise ValueError(f"categorias de texto ausentes no regras.yaml: {faltando}")
        if len(presentes) != len(set(presentes)):
            raise ValueError(f"categoria repetida no regras.yaml: {presentes}")
        return self

    @model_validator(mode="after")
    def _terminacoes_abusadas_sao_extraidas(self) -> Self:
        """Sem isso, `golpe.cfd` escrito sem `http://` nem chegaria ao DomainAnalyzer."""
        fora = sorted(self.dominios.tlds_abusados - self.urls.tlds_conhecidos)
        if fora:
            raise ValueError(f"terminação abusada fora de urls.tlds_conhecidos: {fora}")
        return self


@lru_cache
def carregar_regras() -> Regras:
    """Lê e valida o `regras.yaml`. Chamado em `criar_app()` para que o erro apareça no boot."""
    with CAMINHO_REGRAS.open(encoding="utf-8") as arquivo:
        # `safe_load`, nunca `load`: o YAML é nosso, mas `load` constrói objetos Python
        # arbitrários e não há motivo para deixar essa porta aberta.
        return Regras.model_validate(yaml.safe_load(arquivo))
