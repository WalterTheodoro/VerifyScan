"""Registro da análise no banco — mesmo padrão do `VerificadorSaude`: um Protocol, uma
implementação real e um falso em memória nos testes.
"""

import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Analise, IndicadorRisco
from app.schemas.analise import ExplicacaoIA, Fator, NivelRisco, RespostaAnalise, TipoInput
from app.scoring.combinacao import combinar


@dataclass(frozen=True)
class RegistroAnalise:
    """Tudo o que o banco recebe de uma análise — e nada além disso.

    Não há campo para as URLs (ADR-0009 preserva a query, que pode carregar e-mail ou token da
    vítima). A regra fica no tipo: o repositório não tem por onde recebê-las.

    `usuario_id` é o dono, quando a análise foi feita logado (ADR-0015): um id, não conteúdo.
    `texto_input` é a mensagem, e só existe junto com o dono (ADR-0018). Quem preenche os dois é
    o orquestrador, depois de resolver a sessão.

    `nivel_motor`, `nivel_ia` e `ia_modelo` não carregam conteúdo e vão em toda análise: são o
    que permite medir quantas vezes a IA subiu o nível. `explicacao_ia` é texto livre escrito a
    partir da mensagem e segue a regra do `texto_input` (ADR-0020).
    """

    score: int
    nivel_risco: NivelRisco
    tipo_input: TipoInput
    fatores: tuple[Fator, ...]
    usuario_id: uuid.UUID | None = None
    texto_input: str | None = None
    nivel_motor: NivelRisco | None = None
    nivel_ia: NivelRisco | None = None
    ia_modelo: str | None = None
    explicacao_ia: ExplicacaoIA | None = None

    def __post_init__(self) -> None:
        """As regras dos CHECKs da 0004 e da 0005, no tipo: o erro aparece aqui, e não como um
        registro descartado depois. Texto de OCR nunca é guardado (ADR-0006)."""
        if self.texto_input is not None and self.usuario_id is None:
            raise ValueError("Texto da análise só pode ser guardado com dono (ADR-0018).")
        if self.texto_input is not None and self.tipo_input != "texto":
            raise ValueError("Só a mensagem colada é guardada, nunca texto de OCR (ADR-0006).")
        if self.explicacao_ia is not None and self.usuario_id is None:
            raise ValueError("A explicação da IA só pode ser guardada com dono (ADR-0020).")
        if self.explicacao_ia is not None and self.nivel_ia is None:
            raise ValueError("Explicação da IA sem o nível da IA (ADR-0020).")
        if (self.nivel_ia is None) != (self.ia_modelo is None):
            raise ValueError("O nível da IA e o modelo andam juntos (ADR-0020).")
        if self.nivel_motor is not None and self.nivel_risco != combinar(
            self.nivel_motor, self.nivel_ia
        ):
            raise ValueError("O nível final precisa ser o maior entre o do motor e o da IA.")

    @classmethod
    def da_resposta(
        cls, resposta: RespostaAnalise, tipo_input: TipoInput, ia_modelo: str | None = None
    ) -> "RegistroAnalise":
        """Sem dono, sem texto e sem explicação: quem os acrescenta é o orquestrador, depois de
        resolver a sessão."""
        return cls(
            score=resposta.score,
            nivel_risco=resposta.nivel_risco,
            tipo_input=tipo_input,
            fatores=tuple(resposta.fatores),
            nivel_motor=resposta.nivel_motor,
            nivel_ia=resposta.nivel_ia,
            ia_modelo=ia_modelo,
        )


class RepositorioAnalises(Protocol):
    async def registrar(self, registro: RegistroAnalise) -> uuid.UUID: ...


class RepositorioAnalisesPostgres:
    def __init__(self, fabrica_de_sessoes: async_sessionmaker[AsyncSession]) -> None:
        self._fabrica_de_sessoes = fabrica_de_sessoes

    async def registrar(self, registro: RegistroAnalise) -> uuid.UUID:
        """Grava a análise e todos os indicadores numa transação só (invariante 6).

        Se qualquer insert falhar, o `begin()` desfaz tudo: nunca análise sem indicador nem
        conjunto parcial.
        """
        analise = Analise(
            score_risco=registro.score,
            nivel_risco=registro.nivel_risco,
            tipo_input=registro.tipo_input,
            usuario_id=registro.usuario_id,
            texto_input=registro.texto_input,
            nivel_motor=registro.nivel_motor,
            nivel_ia=registro.nivel_ia,
            ia_modelo=registro.ia_modelo,
            explicacao_ia=(
                registro.explicacao_ia.model_dump(mode="json")
                if registro.explicacao_ia is not None
                else None
            ),
            indicadores=[
                IndicadorRisco(
                    tipo=fator.tipo,
                    categoria=fator.categoria,
                    descricao=fator.descricao,
                    peso=fator.peso,
                )
                for fator in registro.fatores
            ],
        )
        async with self._fabrica_de_sessoes() as sessao, sessao.begin():
            sessao.add(analise)
        return analise.id
