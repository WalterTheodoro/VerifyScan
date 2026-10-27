"""Contrato de `POST /api/analises` e o vocabulário compartilhado da análise.

`NivelRisco`, `TipoFator`, `CategoriaFator` e `Fator` vivem aqui, e não em cada módulo, porque
são o contrato: é o que a API devolve, o que o `ScoringEngine` agrega e o que, na Fase 8, vira
`IndicadorRisco` no banco. Ter um vocabulário só evita um tipo de domínio e um espelho dele.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

NivelRisco = Literal["BAIXO", "MEDIO", "ALTO"]
"""Sem acento no fio: o valor atravessa JSON, banco e enum. A tela é que escreve 'MÉDIO'."""

TipoFator = Literal["texto", "dominio", "reputacao"]
"""De onde o fator veio. Diverge da §5.5 do RFC de propósito — ver errata, item 8.

O RFC fixa (url/texto/dominio/ocr/email). `url` é grosseiro: na arquitetura real ele se divide
em `dominio` (Fase 3) e `reputacao` (Fase 4), que têm origem e peso distintos. `ocr` não é tipo
de indicador — texto extraído de imagem produz fator de texto, e quem registra a origem é
`Analise.tipo_input`. `email` sai com o EmailAnalyzer, cortado do escopo.
"""

TipoInput = Literal["texto"]
"""Como a mensagem chegou: é a procedência que a errata (item 8) tirou de `TipoFator`.

Hoje só texto. `imagem` entra com o OCR (Fase 5), por migração que amplia o CHECK.
"""

CategoriaFator = Literal[
    "urgencia",
    "personificacao_marca",
    "ameaca_bloqueio",
    "premio_falso",
    "solicitacao_financeira",
    "dados_pessoais",
]
"""Unidade de agregação: cada categoria pontua no máximo uma vez (ADR-0004).

As seis são as da §5.4.1 do RFC. As categorias de domínio e reputação entram nas Fases 3 e 4.
"""


class Fator(BaseModel):
    """Um motivo pelo qual a mensagem pontuou.

    `descricao` é sempre um template do `regras.yaml` já renderizado — nunca texto livre e
    nunca um trecho da mensagem do usuário (invariante 1 / ADR-0004).
    """

    tipo: TipoFator
    categoria: CategoriaFator
    descricao: str
    peso: int = Field(gt=0, description="Pontos que este fator soma ao score.")


class Orientacao(BaseModel):
    """A resposta fixa de um nível, lida do `scoring/respostas.yaml` (ADR-0020).

    É o plano B inteiro quando a IA não entra, e o título (e o texto do BAIXO) quando ela entra.
    """

    model_config = ConfigDict(frozen=True)

    titulo: str = Field(min_length=1)
    texto: str | None = None
    passos: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _texto_ou_passos(self) -> Self:
        if not self.texto and not self.passos:
            raise ValueError("cada nível precisa de um texto ou de passos")
        return self


# Tetos do que a IA escreve, em caracteres. A limpeza (`formulator/limpeza.py`) corta no limite;
# o schema garante que nada maior chegue à tela nem ao banco.
TIPO_MAX_CARACTERES = 80
ITEM_MAX_CARACTERES = 220
SINAIS_MAX = 5
PASSOS_MIN = 2
PASSOS_MAX = 4

ItemDaIA = Annotated[str, Field(min_length=1, max_length=ITEM_MAX_CARACTERES)]


class ExplicacaoIA(BaseModel):
    """O que a IA escreveu sobre a mensagem, já limpo: sem link, e-mail, telefone nem HTML.

    É texto livre escrito a partir da mensagem e pode repetir trechos dela (um nome, um valor).
    Por isso segue no banco a mesma regra do `texto_input`: só com dono, e só pela janela do
    histórico (ADR-0020).
    """

    model_config = ConfigDict(frozen=True)

    tipo: str = Field(min_length=1, max_length=TIPO_MAX_CARACTERES)
    sinais: tuple[ItemDaIA, ...] = Field(max_length=SINAIS_MAX)
    o_que_fazer: tuple[ItemDaIA, ...] = Field(min_length=PASSOS_MIN, max_length=PASSOS_MAX)


class SolicitacaoAnalise(BaseModel):
    """Corpo de `POST /api/analises`.

    O tamanho não é limitado aqui, e sim no service: o limite é configurável e a recusa
    precisa sair com uma frase em pt-BR que o usuário entenda, não com o erro de validação
    padrão do FastAPI.
    """

    texto: str = Field(description="A mensagem suspeita, como o usuário a recebeu.")


class RespostaAnalise(BaseModel):
    """O que o usuário recebe: quanto pontuou, em que nível caiu e por quê.

    `score` e `fatores` são sempre do motor. `nivel_risco` é o final: o maior entre o do motor e
    o sugerido pela IA (ADR-0020).
    """

    score: int
    nivel_risco: NivelRisco
    fatores: list[Fator]
    urls_analisadas: list[str] = Field(
        default_factory=list,
        description=(
            "Links encontrados na mensagem, em forma canônica. Populado desde a Fase 1; "
            "quem pontua em cima deles são as Fases 3 e 4."
        ),
    )

    # Campos aditivos da fatia 6 (ADR-0020).
    nivel_motor: NivelRisco = Field(description="O nível que o motor deu sozinho.")
    nivel_ia: NivelRisco | None = Field(
        default=None, description="O nível sugerido pela IA; `null` quando ela não entrou."
    )
    orientacao: Orientacao = Field(description="A resposta fixa do nível final (plano B).")
    explicacao_ia: ExplicacaoIA | None = Field(
        default=None,
        description="Tipo, sinais e passos escritos pela IA para esta mensagem, já limpos.",
    )

    # As flags são a face visível das invariantes 3 e 4: a análise nunca falha por causa da IA
    # nem das APIs externas — degrada e avisa.
    explicacao_indisponivel: bool = Field(
        default=True,
        description=(
            "`true` sempre que a resposta saiu sem a IA: desligada, fora do ar, acima do teto "
            "de tempo ou com uma resposta inválida (RNF08). A tela mostra então o plano B."
        ),
    )
    verificacao_externa_indisponivel: bool = Field(
        default=False,
        description="`true` quando VirusTotal / Safe Browsing não responderam (RNF09).",
    )

    # Campo aditivo da fatia 4 (ADR-0015): quem não o conhece, ignora. Diz à tela se pode
    # afirmar "foi salva no seu histórico" — a frase só é verdade quando o registro gravou o dono.
    salva_no_historico: bool = Field(
        default=False,
        description=(
            "`true` só quando a análise foi gravada ligada à conta de quem está logado. Sem "
            "sessão, com sessão vencida ou com o registro descartado, `false`."
        ),
    )

    # Campo aditivo da fatia 5 (ADR-0018): a tela só diz "salva com a mensagem" quando é verdade.
    texto_salvo: bool = Field(
        default=False,
        description=(
            "`true` só quando a análise foi gravada com dono e com a mensagem, que fica no "
            "histórico pela janela de `HISTORICO_DIAS`. Anônima ou com o registro descartado, "
            "`false`."
        ),
    )
