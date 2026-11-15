"""A hora e o dia da cota (fatia 10, ADR-0024).

O dia da cota vira à meia-noite de São Paulo, e não à de UTC: para quem usa, "hoje" é o dia do
relógio da parede. O relógio entra por injeção (`Relogio`), para o teste mover o tempo sem
esperar.

O fuso é carregado na importação: sem o banco de fusos (o `tzdata`), o processo nem sobe, em vez
de falhar na primeira análise.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

FUSO_DA_COTA = ZoneInfo("America/Sao_Paulo")

Relogio = Callable[[], datetime]


def agora_utc() -> datetime:
    return datetime.now(UTC)


def dia_de_sao_paulo(agora: datetime) -> date:
    return agora.astimezone(FUSO_DA_COTA).date()
