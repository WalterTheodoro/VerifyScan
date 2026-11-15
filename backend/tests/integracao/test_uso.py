"""Uso diário e gasto da IA contra o Postgres real (fatia 10, ADR-0024).

O que só o banco prova: o UPSERT com limite (`ON CONFLICT … DO UPDATE … WHERE`), a atomicidade com
pedidos simultâneos, o aviso de teto uma vez só e os CHECKs da 0007.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models import GastoDiarioIA, UsoDiario
from app.services.repositorio_uso import GastoDaChamada, RepositorioUsoPostgres

pytestmark = pytest.mark.integracao

HOJE = date(2026, 11, 14)


@pytest.fixture
def repositorio(fabrica_de_sessoes: async_sessionmaker[AsyncSession]) -> RepositorioUsoPostgres:
    return RepositorioUsoPostgres(fabrica_de_sessoes)


async def test_reserva_soma_ate_o_limite_e_depois_nega(repositorio: RepositorioUsoPostgres) -> None:
    reservas = [await repositorio.reservar("ia", "ip:abc", HOJE, 1, 5) for _ in range(6)]

    assert [r.concedida for r in reservas] == [True] * 5 + [False]
    assert [r.usadas for r in reservas] == [1, 2, 3, 4, 5, 5]


async def test_print_que_nao_cabe_e_negado_sem_gastar(repositorio: RepositorioUsoPostgres) -> None:
    await repositorio.reservar("ia", "ip:abc", HOJE, 3, 5)

    negada = await repositorio.reservar("ia", "ip:abc", HOJE, 3, 5)
    texto = await repositorio.reservar("ia", "ip:abc", HOJE, 1, 5)

    assert (negada.concedida, negada.usadas) == (False, 3)
    assert (texto.concedida, texto.usadas) == (True, 4)


async def test_chave_finalidade_e_dia_separam_as_contas(
    repositorio: RepositorioUsoPostgres,
) -> None:
    for _ in range(5):
        await repositorio.reservar("ia", "ip:abc", HOJE, 1, 5)

    assert (await repositorio.reservar("ia", "ip:outro", HOJE, 1, 5)).concedida
    assert (await repositorio.reservar("cadastro", "ip:abc", HOJE, 1, 5)).concedida
    assert (await repositorio.reservar("ia", "ip:abc", HOJE + timedelta(days=1), 1, 5)).concedida


async def test_unidades_acima_do_limite_nao_gravam_linha(
    repositorio: RepositorioUsoPostgres, fabrica_de_sessoes: async_sessionmaker[AsyncSession]
) -> None:
    reserva = await repositorio.reservar("ia", "ip:abc", HOJE, 3, 2)

    assert not reserva.concedida
    async with fabrica_de_sessoes() as sessao:
        assert (await sessao.scalars(select(UsoDiario))).all() == []


async def test_gasto_soma_os_cinco_campos(repositorio: RepositorioUsoPostgres) -> None:
    await repositorio.somar_gasto(HOJE, GastoDaChamada(1000, 200, Decimal("0.0002"), 1, 0))
    total = await repositorio.somar_gasto(HOJE, GastoDaChamada(0, 0, Decimal(0), 0, 1))

    assert total == Decimal("0.000200")
    assert await repositorio.gasto_do_dia(HOJE) == Decimal("0.000200")
    assert await repositorio.gasto_do_dia(HOJE - timedelta(days=1)) == 0


async def test_aviso_de_teto_e_marcado_uma_vez_so(repositorio: RepositorioUsoPostgres) -> None:
    teto = Decimal("0.001")
    await repositorio.somar_gasto(HOJE, GastoDaChamada(0, 0, Decimal("0.0005"), 1, 0))
    assert not await repositorio.marcar_teto_avisado(HOJE, teto)

    await repositorio.somar_gasto(HOJE, GastoDaChamada(0, 0, Decimal("0.0005"), 1, 0))

    assert await repositorio.marcar_teto_avisado(HOJE, teto)
    assert not await repositorio.marcar_teto_avisado(HOJE, teto)


async def test_faxina_apaga_o_uso_antigo_e_mantem_o_gasto(
    repositorio: RepositorioUsoPostgres, fabrica_de_sessoes: async_sessionmaker[AsyncSession]
) -> None:
    for dias_atras in range(4):
        await repositorio.reservar("ia", "ip:abc", HOJE - timedelta(days=dias_atras), 1, 5)
    await repositorio.somar_gasto(
        HOJE - timedelta(days=30), GastoDaChamada(1, 1, Decimal("0.000001"), 1, 0)
    )

    apagadas = await repositorio.apagar_antigos(HOJE - timedelta(days=1))

    assert apagadas == 2
    async with fabrica_de_sessoes() as sessao:
        dias = sorted((await sessao.scalars(select(UsoDiario.dia))).all())
        gastos = (await sessao.scalars(select(GastoDiarioIA.dia))).all()
    assert dias == [HOJE - timedelta(days=1), HOJE]
    assert gastos == [HOJE - timedelta(days=30)]


@pytest.mark.parametrize(
    "instrucao",
    [
        "INSERT INTO uso_diario (finalidade, chave, dia, unidades) "
        "VALUES ('outra', 'ip:abc', '2026-11-14', 1)",
        "INSERT INTO uso_diario (finalidade, chave, dia, unidades) "
        "VALUES ('ia', 'ip:abc', '2026-11-14', 0)",
        "INSERT INTO gasto_diario_ia (dia, custo_usd) VALUES ('2026-11-14', -1)",
        "INSERT INTO gasto_diario_ia (dia, chamadas_com_timeout) VALUES ('2026-11-14', -1)",
    ],
)
async def test_checks_da_0007(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession], instrucao: str
) -> None:
    with pytest.raises(IntegrityError):
        async with fabrica_de_sessoes() as sessao, sessao.begin():
            await sessao.execute(text(instrucao))


# ─── pedidos simultâneos ──────────────────────────────────────────────────────────────────


@pytest.fixture
async def fabrica_com_commit(
    url_banco_de_teste: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Conexões separadas, com commit de verdade: é o único jeito de N pedidos disputarem a mesma
    linha. A `fabrica_de_sessoes` põe tudo numa conexão só, onde os pedidos sairiam em série e um
    código que lê, confere e grava em três passos passaria do mesmo jeito.

    As linhas são apagadas no fim: o requisito "nenhum teste deixa linha" vale aqui também.
    """
    engine = create_async_engine(url_banco_de_teste, poolclass=NullPool)
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield fabrica
    finally:
        async with fabrica() as sessao, sessao.begin():
            await sessao.execute(delete(UsoDiario))
            await sessao.execute(delete(GastoDiarioIA))
        await engine.dispose()


@pytest.mark.parametrize(("unidades", "concedidas"), [(1, 5), (3, 1)])
async def test_pedidos_simultaneos_respeitam_a_cota_exatamente(
    fabrica_com_commit: async_sessionmaker[AsyncSession], unidades: int, concedidas: int
) -> None:
    """20 pedidos ao mesmo tempo, cota de 5: exatamente 5 textos (ou 1 print) passam."""
    repositorio = RepositorioUsoPostgres(fabrica_com_commit)

    reservas = await asyncio.gather(
        *(repositorio.reservar("ia", "ip:corrida", HOJE, unidades, 5) for _ in range(20))
    )

    assert sum(r.concedida for r in reservas) == concedidas
    async with fabrica_com_commit() as sessao:
        total = await sessao.scalar(
            select(UsoDiario.unidades).where(UsoDiario.chave == "ip:corrida")
        )
    assert total == unidades * concedidas


async def test_gasto_simultaneo_nao_perde_soma(
    fabrica_com_commit: async_sessionmaker[AsyncSession],
) -> None:
    repositorio = RepositorioUsoPostgres(fabrica_com_commit)

    await asyncio.gather(
        *(
            repositorio.somar_gasto(HOJE, GastoDaChamada(100, 10, Decimal("0.000015"), 1, 0))
            for _ in range(20)
        )
    )

    async with fabrica_com_commit() as sessao:
        gasto = await sessao.get(GastoDiarioIA, HOJE)
    assert gasto is not None
    assert (gasto.tokens_entrada, gasto.chamadas) == (2000, 20)
    assert gasto.custo_usd == Decimal("0.000300")
