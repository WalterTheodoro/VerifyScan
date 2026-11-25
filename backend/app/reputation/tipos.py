"""Vocabulário da reputação de links (ADR-0028)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.schemas.analise import FonteReputacao

Veredito = Literal["limpo", "suspeito", "malicioso"]
"""O que uma base disse de um domínio. `limpo` é só "não apontou": nunca vira frase de segurança."""

MotivoDaFalha = Literal["sem_chave", "timeout", "limite", "cota_local", "http", "resposta", "erro"]
"""Por que uma base não respondeu. Conjunto fechado: é rótulo de métrica (ADR-0026).

`limite` é o 429 da base; `cota_local` é o nosso contador do VirusTotal, que parou antes."""


def para_consulta(nome: str) -> str:
    """O host como vai na consulta: em ASCII (`xn--…`) quando tem letra de fora do ASCII."""
    try:
        return nome.encode("idna").decode("ascii")
    except UnicodeError:
        return nome


class FonteIndisponivel(Exception):
    """A base não respondeu. Leva só o motivo: nunca a URL chamada (a do Safe Browsing tem a
    chave na query) nem o domínio consultado."""

    def __init__(self, motivo: MotivoDaFalha) -> None:
        super().__init__(motivo)
        self.motivo: MotivoDaFalha = motivo


@dataclass(frozen=True)
class Alvo:
    """Um link a consultar, reduzido ao que pode sair do processo: o host e o domínio
    registrável. Nunca o caminho, a query nem o fragmento."""

    host: str
    dominio: str
    numerico: bool = False


@dataclass(frozen=True)
class Apontamento:
    """Uma base apontou um domínio. `dominio` é o registrável, o mesmo do bloco de links."""

    dominio: str
    fonte: FonteReputacao
    veredito: Veredito


@dataclass(frozen=True)
class ItemDeCache:
    """Uma resposta a guardar. `chave` é o SHA-256 do que foi consultado, nunca o domínio."""

    fonte: FonteReputacao
    chave: str
    veredito: Veredito
    expira_em: datetime


@dataclass(frozen=True)
class ResultadoReputacao:
    """O que a etapa apurou. `indisponivel`: havia domínio para consultar e alguma base não
    respondeu. `a_guardar` vai para o cache depois, fora do teto da etapa."""

    apontamentos: tuple[Apontamento, ...] = ()
    indisponivel: bool = False
    a_guardar: tuple[ItemDeCache, ...] = ()
