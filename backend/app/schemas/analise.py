"""Contrato de `POST /api/analises` e o vocabulário compartilhado da análise.

`NivelRisco`, `TipoFator`, `CategoriaFator` e `Fator` vivem aqui, e não em cada módulo, porque
são o contrato: é o que a API devolve, o que o `ScoringEngine` agrega e o que, na Fase 8, vira
`IndicadorRisco` no banco. Ter um vocabulário só evita um tipo de domínio e um espelho dele.
"""

from typing import Literal

from pydantic import BaseModel, Field

NivelRisco = Literal["BAIXO", "MEDIO", "ALTO"]
"""Sem acento no fio: o valor atravessa JSON, banco e enum. A tela é que escreve 'MÉDIO'."""

TipoFator = Literal["texto", "dominio", "reputacao"]
"""De onde o fator veio. Diverge da §5.5 do RFC de propósito — ver errata, item 8.

O RFC fixa (url/texto/dominio/ocr/email). `url` é grosseiro: na arquitetura real ele se divide
em `dominio` (Fase 3) e `reputacao` (Fase 4), que têm origem e peso distintos. `ocr` não é tipo
de indicador — texto extraído de imagem produz fator de texto, e quem registra a origem é
`Analise.tipo_input`. `email` sai com o EmailAnalyzer, cortado do escopo.
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


class SolicitacaoAnalise(BaseModel):
    """Corpo de `POST /api/analises`.

    O tamanho não é limitado aqui, e sim no service: o limite é configurável e a recusa
    precisa sair com uma frase em pt-BR que o usuário entenda, não com o erro de validação
    padrão do FastAPI.
    """

    texto: str = Field(description="A mensagem suspeita, como o usuário a recebeu.")


class RespostaAnalise(BaseModel):
    """O que o usuário recebe: quanto pontuou, em que nível caiu e por quê."""

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

    # As duas flags entram no contrato agora, valendo sempre `false`, para que ligá-las nas
    # Fases 4 e 7 não seja mudança de contrato. Elas são a face visível das invariantes 3 e 4:
    # a análise nunca falha por causa da IA nem das APIs externas — degrada e avisa.
    explicacao_indisponivel: bool = Field(
        default=False,
        description="`true` quando a LLM não respondeu a tempo e falta a explicação (RNF08).",
    )
    verificacao_externa_indisponivel: bool = Field(
        default=False,
        description="`true` quando VirusTotal / Safe Browsing não responderam (RNF09).",
    )
