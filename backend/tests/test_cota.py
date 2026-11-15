"""Cota diária da IA e teto global de gasto (fatia 10, ADR-0024), com o repositório em memória.

O UPSERT de verdade, com pedidos simultâneos, é provado contra o Postgres em
`tests/integracao/test_uso.py`.
"""

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.formulator.cliente import ConsumoDaIA, RespostaIA
from app.services.cota import UNIDADES_PRINT, UNIDADES_TEXTO, ServicoCota
from tests.conftest import RelogioFalso, RepositorioUsoEmMemoria

ANA = "conta:ana"
VISITANTE = "ip:abc"


def _servico(
    uso: RepositorioUsoEmMemoria, relogio: RelogioFalso, **mudancas: object
) -> ServicoCota:
    valores: dict[str, object] = {
        "cota_sem_conta": 5,
        "cota_com_conta": 25,
        "teto_usd": Decimal("1.00"),
        "preco_entrada_por_milhao": Decimal("0.10"),
        "preco_saida_por_milhao": Decimal("0.50"),
        "cadastros_por_ip": 5,
    }
    valores.update(mudancas)
    return ServicoCota(uso, relogio, **valores)  # type: ignore[arg-type]


def _consumo(entrada: int, saida: int, *, timeouts: int = 0) -> ConsumoDaIA:
    consumo = ConsumoDaIA()
    if entrada or saida:
        consumo.somar(RespostaIA("{}", "end_turn", "m", entrada, saida))
    for _ in range(timeouts):
        consumo.contar_timeout()
    return consumo


@pytest.fixture
def uso() -> RepositorioUsoEmMemoria:
    return RepositorioUsoEmMemoria()


async def test_sem_conta_sao_5_unidades_por_dia(
    uso: RepositorioUsoEmMemoria, relogio: RelogioFalso
) -> None:
    cota = _servico(uso, relogio)
    dia = cota.hoje()

    situacoes = [await cota.reservar_ia(VISITANTE, False, UNIDADES_TEXTO, dia) for _ in range(6)]

    assert [s.concedida for s in situacoes] == [True] * 5 + [False]
    assert [s.restantes for s in situacoes] == [4, 3, 2, 1, 0, 0]


async def test_com_conta_sao_25_unidades_por_dia(
    uso: RepositorioUsoEmMemoria, relogio: RelogioFalso
) -> None:
    cota = _servico(uso, relogio)
    dia = cota.hoje()

    situacoes = [await cota.reservar_ia(ANA, True, UNIDADES_TEXTO, dia) for _ in range(26)]

    assert sum(s.concedida for s in situacoes) == 25
    assert situacoes[0].restantes == 24


async def test_cada_chave_tem_a_propria_cota(
    uso: RepositorioUsoEmMemoria, relogio: RelogioFalso
) -> None:
    cota = _servico(uso, relogio)
    dia = cota.hoje()
    for _ in range(5):
        await cota.reservar_ia(VISITANTE, False, UNIDADES_TEXTO, dia)

    outro = await cota.reservar_ia("ip:outro", False, UNIDADES_TEXTO, dia)

    assert outro.concedida
    assert outro.restantes == 4


async def test_a_cota_volta_a_meia_noite_de_sao_paulo(
    uso: RepositorioUsoEmMemoria, relogio: RelogioFalso
) -> None:
    cota = _servico(uso, relogio)
    relogio.agora = datetime(2026, 11, 15, 2, 50, tzinfo=UTC)  # 23:50 de 14/11 em São Paulo
    for _ in range(5):
        await cota.reservar_ia(VISITANTE, False, UNIDADES_TEXTO, cota.hoje())
    assert not (await cota.reservar_ia(VISITANTE, False, UNIDADES_TEXTO, cota.hoje())).concedida

    relogio.agora += timedelta(minutes=9)  # 23:59 em São Paulo: ainda o mesmo dia
    assert not (await cota.reservar_ia(VISITANTE, False, UNIDADES_TEXTO, cota.hoje())).concedida

    relogio.agora += timedelta(minutes=1)  # 00:00 em São Paulo
    assert cota.hoje() == date(2026, 11, 15)
    assert (await cota.reservar_ia(VISITANTE, False, UNIDADES_TEXTO, cota.hoje())).concedida


async def test_print_custa_3_unidades(uso: RepositorioUsoEmMemoria, relogio: RelogioFalso) -> None:
    cota = _servico(uso, relogio)
    dia = cota.hoje()

    situacao = await cota.reservar_ia(VISITANTE, False, UNIDADES_PRINT, dia)

    assert UNIDADES_PRINT == 3
    assert situacao.concedida
    assert situacao.restantes == 2


async def test_print_com_2_restantes_e_negado_e_o_texto_ainda_passa(
    uso: RepositorioUsoEmMemoria, relogio: RelogioFalso
) -> None:
    cota = _servico(uso, relogio)
    dia = cota.hoje()
    await cota.reservar_ia(VISITANTE, False, UNIDADES_PRINT, dia)

    negado = await cota.reservar_ia(VISITANTE, False, UNIDADES_PRINT, dia)
    texto = await cota.reservar_ia(VISITANTE, False, UNIDADES_TEXTO, dia)

    assert not negado.concedida
    assert negado.restantes == 2  # a recusa não gastou nada
    assert texto.concedida
    assert texto.restantes == 1


async def test_cota_menor_que_o_print_recusa_sem_gravar(
    uso: RepositorioUsoEmMemoria, relogio: RelogioFalso
) -> None:
    cota = _servico(uso, relogio, cota_sem_conta=2)

    situacao = await cota.reservar_ia(VISITANTE, False, UNIDADES_PRINT, cota.hoje())

    assert not situacao.concedida
    assert situacao.restantes == 2
    assert uso.usos == {}


async def test_teto_global_atingido_nega_a_todos_com_zero_restantes(
    uso: RepositorioUsoEmMemoria, relogio: RelogioFalso
) -> None:
    cota = _servico(uso, relogio, teto_usd=Decimal("0.001"))
    dia = cota.hoje()
    # 10 mil tokens de entrada a US$ 0,10/M = US$ 0,001: exatamente o teto.
    await cota.registrar_gasto(_consumo(10_000, 0), dia, timeout_s=1)

    sem_conta = await cota.reservar_ia(VISITANTE, False, UNIDADES_TEXTO, dia)
    com_conta = await cota.reservar_ia(ANA, True, UNIDADES_TEXTO, dia)

    assert not sem_conta.concedida
    assert not com_conta.concedida
    assert sem_conta.restantes == com_conta.restantes == 0
    # Negar pelo teto não gasta a cota de ninguém.
    assert uso.usos == {}


async def test_o_teto_vale_so_para_o_dia(
    uso: RepositorioUsoEmMemoria, relogio: RelogioFalso
) -> None:
    cota = _servico(uso, relogio, teto_usd=Decimal("0.001"))
    await cota.registrar_gasto(_consumo(10_000, 0), cota.hoje(), timeout_s=1)

    relogio.agora += timedelta(days=1)

    assert (await cota.reservar_ia(VISITANTE, False, UNIDADES_TEXTO, cota.hoje())).concedida


async def test_custo_e_calculado_pelo_usage_com_os_precos_do_settings(
    uso: RepositorioUsoEmMemoria, relogio: RelogioFalso
) -> None:
    cota = _servico(uso, relogio)
    dia = cota.hoje()

    # 1000 x 0,10/M + 200 x 0,50/M = 0,0001 + 0,0001
    await cota.registrar_gasto(_consumo(1000, 200), dia, timeout_s=1)
    await cota.registrar_gasto(_consumo(1000, 200), dia, timeout_s=1)

    gasto = uso.gastos[dia]
    assert gasto.custo_usd == Decimal("0.000400")
    assert (gasto.tokens_entrada, gasto.tokens_saida, gasto.chamadas) == (2000, 400, 2)
    assert gasto.chamadas_com_timeout == 0


async def test_timeout_entra_na_contagem_e_nao_no_custo(
    uso: RepositorioUsoEmMemoria, relogio: RelogioFalso
) -> None:
    cota = _servico(uso, relogio)
    dia = cota.hoje()

    await cota.registrar_gasto(_consumo(0, 0, timeouts=1), dia, timeout_s=1)

    gasto = uso.gastos[dia]
    assert gasto.chamadas_com_timeout == 1
    assert gasto.chamadas == 0
    assert gasto.custo_usd == 0


async def test_consumo_vazio_nao_grava(uso: RepositorioUsoEmMemoria, relogio: RelogioFalso) -> None:
    cota = _servico(uso, relogio)

    await cota.registrar_gasto(ConsumoDaIA(), cota.hoje(), timeout_s=1)

    assert uso.gastos == {}


async def test_aviso_de_teto_sai_uma_vez_so(
    uso: RepositorioUsoEmMemoria, relogio: RelogioFalso, caplog: pytest.LogCaptureFixture
) -> None:
    cota = _servico(uso, relogio, teto_usd=Decimal("0.001"))
    dia = cota.hoje()

    with caplog.at_level(logging.WARNING, logger="app"):
        for _ in range(3):
            await cota.registrar_gasto(_consumo(10_000, 0), dia, timeout_s=1)

    avisos = [r for r in caplog.records if "Teto diário de gasto" in r.getMessage()]
    assert len(avisos) == 1


async def test_falha_ao_registrar_o_gasto_so_loga(
    relogio: RelogioFalso, caplog: pytest.LogCaptureFixture
) -> None:
    class UsoQueFalha(RepositorioUsoEmMemoria):
        async def somar_gasto(self, dia: date, gasto: object) -> Decimal:
            raise RuntimeError("falhou com dado sensível 203.0.113.9")

    cota = _servico(UsoQueFalha(), relogio)

    with caplog.at_level(logging.WARNING, logger="app"):
        await cota.registrar_gasto(_consumo(1000, 200), cota.hoje(), timeout_s=1)

    assert "RuntimeError" in caplog.text
    assert "203.0.113.9" not in caplog.text


async def test_gasto_lento_estoura_o_teto_e_so_loga(
    relogio: RelogioFalso, caplog: pytest.LogCaptureFixture
) -> None:
    import asyncio

    class UsoLento(RepositorioUsoEmMemoria):
        async def somar_gasto(self, dia: date, gasto: object) -> Decimal:
            await asyncio.sleep(3600)
            raise AssertionError("o timeout deveria ter cortado antes")

    cota = _servico(UsoLento(), relogio)

    with caplog.at_level(logging.WARNING, logger="app"):
        await cota.registrar_gasto(_consumo(1000, 200), cota.hoje(), timeout_s=0.05)

    assert "TimeoutError" in caplog.text


async def test_cadastro_limitado_por_ip_por_dia(
    uso: RepositorioUsoEmMemoria, relogio: RelogioFalso
) -> None:
    cota = _servico(uso, relogio)

    resultados = [await cota.reservar_cadastro("abc") for _ in range(6)]

    assert resultados == [True] * 5 + [False]
    relogio.agora += timedelta(days=1)
    assert await cota.reservar_cadastro("abc")


async def test_cadastro_e_ia_contam_separado(
    uso: RepositorioUsoEmMemoria, relogio: RelogioFalso
) -> None:
    cota = _servico(uso, relogio)
    for _ in range(5):
        await cota.reservar_cadastro(VISITANTE.removeprefix("ip:"))

    assert (await cota.reservar_ia(VISITANTE, False, UNIDADES_TEXTO, cota.hoje())).concedida
