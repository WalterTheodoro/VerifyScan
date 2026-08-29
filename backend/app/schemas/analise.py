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
