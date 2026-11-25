"""Cache e contador da reputação contra o Postgres real (ADR-0028, migração 0008).

O que só o banco prova: a reserva nos dois limites numa transação (a soma do minuto é desfeita se
a do dia não couber), a atomicidade com pedidos simultâneos, a leitura que ignora o vencido, a
limpeza ao gravar e os CHECKs.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import ReputacaoCache, ReputacaoUso
from app.reputation.tipos import ItemDeCache
from app.services.repositorio_reputacao import RepositorioReputacaoPostgres

pytestmark = pytest.mark.integracao

AGORA = datetime(2026, 11, 25, 15, 30, 20, tzinfo=UTC)
CHAVE = "a" * 64


@pytest.fixture
def repositorio(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> RepositorioReputacaoPostgres:
    return RepositorioReputacaoPostgres(fabrica_de_sessoes)


async def _consultas(fabrica: async_sessionmaker[AsyncSession]) -> dict[str, int]:
    async with fabrica() as sessao:
        linhas = await sessao.execute(select(ReputacaoUso.janela, ReputacaoUso.consultas))
        return {janela: consultas for janela, consultas in linhas.all()}


async def test_reserva_para_no_limite_do_minuto_e_volta_no_minuto_seguinte(
    repositorio: RepositorioReputacaoPostgres,
) -> None:
    reservas = [await repositorio.reservar("virustotal", AGORA, 1, 4, 500) for _ in range(5)]
    depois = await repositorio.reservar("virustotal", AGORA + timedelta(minutes=1), 1, 4, 500)

    assert reservas == [True] * 4 + [False]
    assert depois is True


async def test_reserva_para_no_limite_do_dia(repositorio: RepositorioReputacaoPostgres) -> None:
    concedidas = [
        await repositorio.reservar("virustotal", AGORA + timedelta(minutes=i), 1, 4, 3)
        for i in range(5)
    ]

    assert concedidas == [True, True, True, False, False]


async def test_dia_cheio_desfaz_a_soma_do_minuto(
    repositorio: RepositorioReputacaoPostgres,
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    """O minuto ainda teria vaga, mas o dia não: nada é somado em lugar nenhum."""
    assert await repositorio.reservar("virustotal", AGORA, 2, 4, 3) is True

    assert await repositorio.reservar("virustotal", AGORA, 2, 4, 3) is False

    assert await _consultas(fabrica_de_sessoes) == {"minuto": 2, "dia": 2}


async def test_pedido_maior_que_o_limite_e_negado_sem_gravar(
    repositorio: RepositorioReputacaoPostgres,
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    assert await repositorio.reservar("virustotal", AGORA, 5, 4, 500) is False
    assert await _consultas(fabrica_de_sessoes) == {}


async def test_reservas_simultaneas_nao_passam_do_limite(
    repositorio: RepositorioReputacaoPostgres,
) -> None:
    reservas = await asyncio.gather(
        *(repositorio.reservar("virustotal", AGORA, 1, 4, 500) for _ in range(10))
    )

    assert sum(reservas) == 4


async def test_cache_devolve_so_o_que_nao_venceu(repositorio: RepositorioReputacaoPostgres) -> None:
    await repositorio.guardar(
        [
            ItemDeCache("virustotal", CHAVE, "malicioso", AGORA + timedelta(hours=24)),
            ItemDeCache("safe_browsing", CHAVE, "malicioso", AGORA + timedelta(seconds=300)),
        ]
    )

    dentro = await repositorio.buscar("safe_browsing", [CHAVE], AGORA + timedelta(seconds=299))
    no_prazo = await repositorio.buscar("safe_browsing", [CHAVE], AGORA + timedelta(seconds=300))
    do_virustotal = await repositorio.buscar("virustotal", [CHAVE, "b" * 64], AGORA)

    assert dentro == {CHAVE: "malicioso"}
    assert no_prazo == {}
    assert do_virustotal == {CHAVE: "malicioso"}


async def test_guardar_de_novo_substitui_o_veredito_e_o_prazo(
    repositorio: RepositorioReputacaoPostgres,
) -> None:
    futuro = datetime.now(UTC) + timedelta(hours=1)
    await repositorio.guardar([ItemDeCache("virustotal", CHAVE, "malicioso", futuro)])

    await repositorio.guardar(
        [ItemDeCache("virustotal", CHAVE, "limpo", futuro + timedelta(hours=1))]
    )

    assert await repositorio.buscar("virustotal", [CHAVE], futuro) == {CHAVE: "limpo"}


async def test_guardar_apaga_o_que_ja_venceu(
    repositorio: RepositorioReputacaoPostgres,
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    """A limpeza usa a hora de verdade: o vencido é de ontem, o válido é de amanhã."""
    agora = datetime.now(UTC)
    await repositorio.guardar(
        [ItemDeCache("virustotal", "b" * 64, "limpo", agora - timedelta(days=1))]
    )
    await repositorio.reservar("virustotal", agora - timedelta(days=3), 1, 4, 500)

    await repositorio.guardar(
        [ItemDeCache("virustotal", CHAVE, "limpo", agora + timedelta(days=1))]
    )

    async with fabrica_de_sessoes() as sessao:
        chaves = (await sessao.scalars(select(ReputacaoCache.chave))).all()
    assert chaves == [CHAVE]
    assert await _consultas(fabrica_de_sessoes) == {}


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO reputacao_cache (fonte, chave, veredito, expira_em) "
        "VALUES ('outra', 'x', 'limpo', now())",
        "INSERT INTO reputacao_cache (fonte, chave, veredito, expira_em) "
        "VALUES ('virustotal', 'x', 'seguro', now())",
        "INSERT INTO reputacao_uso (fonte, janela, inicio, consultas) "
        "VALUES ('virustotal', 'hora', now(), 1)",
        "INSERT INTO reputacao_uso (fonte, janela, inicio, consultas) "
        "VALUES ('virustotal', 'dia', now(), 0)",
    ],
)
async def test_checks_da_0008(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession], sql: str
) -> None:
    async with fabrica_de_sessoes() as sessao:
        with pytest.raises(IntegrityError):
            await sessao.execute(text(sql))
