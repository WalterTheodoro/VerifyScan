"""Eventos de domínio e métricas (ADR-0026): um log por acontecimento, só com metadado.

Os contadores moram num registro do processo, que não zera entre os testes: cada teste mede a
diferença (antes → depois), nunca o valor absoluto.
"""

import logging
from collections.abc import AsyncIterator
from datetime import timedelta
from decimal import Decimal

import anthropic
import httpx2
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.metricas import REGISTRO
from app.formulator.analisador import AnalisadorIA
from app.ocr.imagem import preparar_imagem
from app.ocr.leitura import LeitorDePrint, LeituraFalhou
from tests.conftest import (
    ClienteIAFalso,
    ClienteLeituraFalso,
    RelogioFalso,
    RepositorioUsoEmMemoria,
    corpo_de_print,
    png_de_teste,
    saida_da_ia,
    saida_da_leitura,
)
from tests.test_analisador_ia import ENTRADA, PEDIDO
from tests.test_api_analise_cota import _cotas_de_producao, _ligar_ia, _ligar_leitura
from tests.test_api_analises import GOLPE_DE_PIX
from tests.test_api_autenticacao import CADASTRO, LOGIN
from tests.test_cota import VISITANTE, _consumo, _servico

INOFENSIVA = "Oi, tudo bem? Chego para o almoço ao meio-dia."


@pytest.fixture
async def navegador(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Em https: o cookie de sessão é Secure, e sem ele a conta não acompanha a análise."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://teste") as cliente:
        yield cliente


def _eventos(caplog: pytest.LogCaptureFixture, nome: str) -> list[dict[str, object]]:
    return [
        r.campos  # type: ignore[attr-defined]
        for r in caplog.records
        if getattr(r, "evento", None) == nome
    ]


def _valor(metrica: str, **rotulos: str) -> float:
    return REGISTRO.get_sample_value(metrica, rotulos) or 0.0


# ─── analise_concluida ────────────────────────────────────────────────────────────────────


async def test_analise_de_texto_sem_ia(
    cliente: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    antes = _valor("verifyscan_analises_total", tipo="texto", nivel_final="ALTO")
    medidas = _valor("verifyscan_analise_duracao_segundos_count", tipo="texto")

    with caplog.at_level(logging.INFO, logger="app"):
        await cliente.post("/api/analises", json={"texto": GOLPE_DE_PIX})

    [campos] = _eventos(caplog, "analise_concluida")
    assert campos == {
        "tipo": "texto",
        "nivel_motor": "ALTO",
        "nivel_final": "ALTO",
        "ia_usada": False,
        "ia_subiu_nivel": False,
        "duracao_ms": campos["duracao_ms"],
    }
    assert isinstance(campos["duracao_ms"], int)
    assert _valor("verifyscan_analises_total", tipo="texto", nivel_final="ALTO") == antes + 1
    assert _valor("verifyscan_analise_duracao_segundos_count", tipo="texto") == medidas + 1


async def test_ia_que_sobe_o_nivel(
    app: FastAPI, cliente: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    _ligar_ia(app, ClienteIAFalso(saida_da_ia(nivel_sugerido="ALTO")))
    antes = _valor("verifyscan_ia_subiu_nivel_total")

    with caplog.at_level(logging.INFO, logger="app"):
        await cliente.post("/api/analises", json={"texto": INOFENSIVA})

    [campos] = _eventos(caplog, "analise_concluida")
    assert campos["nivel_motor"] == "BAIXO"
    assert campos["nivel_final"] == "ALTO"
    assert campos["ia_usada"] is True
    assert campos["ia_subiu_nivel"] is True
    assert _valor("verifyscan_ia_subiu_nivel_total") == antes + 1


async def test_ia_que_concorda_nao_conta_como_subida(
    app: FastAPI, cliente: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    _ligar_ia(app, ClienteIAFalso(saida_da_ia(nivel_sugerido="BAIXO")))
    antes = _valor("verifyscan_ia_subiu_nivel_total")

    with caplog.at_level(logging.INFO, logger="app"):
        await cliente.post("/api/analises", json={"texto": INOFENSIVA})

    [campos] = _eventos(caplog, "analise_concluida")
    assert campos["ia_usada"] is True
    assert campos["ia_subiu_nivel"] is False
    assert _valor("verifyscan_ia_subiu_nivel_total") == antes


async def test_analise_de_print(
    app: FastAPI, cliente: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    _ligar_ia(app, ClienteIAFalso())
    _ligar_leitura(app, ClienteLeituraFalso())
    antes = _valor("verifyscan_analise_duracao_segundos_count", tipo="print")

    with caplog.at_level(logging.INFO, logger="app"):
        resposta = await cliente.post("/api/analises/imagem", json=corpo_de_print())

    assert resposta.status_code == 200
    [campos] = _eventos(caplog, "analise_concluida")
    assert campos["tipo"] == "print"
    assert campos["qtd_imagens"] == 1
    assert campos["ia_usada"] is True
    assert _valor("verifyscan_analise_duracao_segundos_count", tipo="print") == antes + 1


async def test_entrada_recusada_nao_e_analise_concluida(
    cliente: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app"):
        resposta = await cliente.post("/api/analises", json={"texto": "   "})

    assert resposta.status_code == 422
    assert _eventos(caplog, "analise_concluida") == []


# ─── ia_falhou ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("cliente_ia", "motivo"),
    [
        (ClienteIAFalso(erro=TimeoutError()), "timeout"),
        (ClienteIAFalso(erro=anthropic.APITimeoutError(request=PEDIDO)), "timeout"),
        (ClienteIAFalso(erro=anthropic.APIConnectionError(request=PEDIDO)), "http"),
        (
            ClienteIAFalso(
                erro=anthropic.RateLimitError(
                    "erro", response=httpx2.Response(429, request=PEDIDO), body=None
                )
            ),
            "http",
        ),
        (ClienteIAFalso(motivo_parada="refusal"), "forma"),
        (ClienteIAFalso(motivo_parada="max_tokens"), "forma"),
        (ClienteIAFalso("isto não é JSON"), "forma"),
        (ClienteIAFalso(erro=RuntimeError("qualquer outra coisa")), "outro"),
    ],
    ids=[
        "nosso-teto",
        "teto-do-sdk",
        "conexao",
        "429",
        "recusa",
        "corte",
        "json-invalido",
        "outro",
    ],
)
async def test_ia_falhou_com_o_motivo_num_conjunto_fechado(
    cliente_ia: ClienteIAFalso, motivo: str, caplog: pytest.LogCaptureFixture
) -> None:
    antes = _valor("verifyscan_ia_falhas_total", motivo=motivo)

    with caplog.at_level(logging.INFO, logger="app"):
        assert await AnalisadorIA(cliente_ia, timeout_s=15).avaliar(ENTRADA) is None

    [campos] = _eventos(caplog, "ia_falhou")
    assert campos["motivo"] == motivo
    assert campos["etapa"] == "analise"
    assert _valor("verifyscan_ia_falhas_total", motivo=motivo) == antes + 1


async def test_ia_desligada_nao_e_falha(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="app"):
        await AnalisadorIA(None, timeout_s=15).avaliar(ENTRADA)

    assert _eventos(caplog, "ia_falhou") == []


async def test_leitura_do_print_que_cai_tambem_e_ia_falhou(
    caplog: pytest.LogCaptureFixture,
) -> None:
    leitor = LeitorDePrint(ClienteLeituraFalso(erro=TimeoutError()), timeout_s=10)
    antes = _valor("verifyscan_ia_falhas_total", motivo="timeout")

    with caplog.at_level(logging.INFO, logger="app"), pytest.raises(LeituraFalhou):
        await leitor.ler(preparar_imagem(png_de_teste(), 5 * 1024 * 1024))

    [campos] = _eventos(caplog, "ia_falhou")
    assert campos == {"motivo": "timeout", "etapa": "leitura"}
    assert _valor("verifyscan_ia_falhas_total", motivo="timeout") == antes + 1


async def test_print_ilegivel_nao_e_falha_da_ia(caplog: pytest.LogCaptureFixture) -> None:
    """A IA respondeu certo: o que não deu para ler foi a imagem."""
    leitor = LeitorDePrint(ClienteLeituraFalso(saida_da_leitura(legivel="nao")), timeout_s=10)

    with caplog.at_level(logging.INFO, logger="app"), pytest.raises(LeituraFalhou):
        await leitor.ler(preparar_imagem(png_de_teste(), 5 * 1024 * 1024))

    assert _eventos(caplog, "ia_falhou") == []


# ─── cota_excedida e teto_global_atingido ─────────────────────────────────────────────────


async def test_cota_excedida_sem_conta(
    app: FastAPI, cliente: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    _cotas_de_producao(app)
    _ligar_ia(app, ClienteIAFalso())
    antes = _valor("verifyscan_cota_excedida_total", com_conta="false")

    with caplog.at_level(logging.INFO, logger="app"):
        for _ in range(6):
            await cliente.post("/api/analises", json={"texto": GOLPE_DE_PIX})

    assert _eventos(caplog, "cota_excedida") == [{"com_conta": False, "teto_global": False}]
    assert _valor("verifyscan_cota_excedida_total", com_conta="false") == antes + 1


async def test_cota_excedida_com_conta(
    app: FastAPI, navegador: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    _cotas_de_producao(app, ia_cota_com_conta=1)
    _ligar_ia(app, ClienteIAFalso())
    await navegador.post("/api/auth/cadastro", json=CADASTRO)
    antes = _valor("verifyscan_cota_excedida_total", com_conta="true")

    with caplog.at_level(logging.INFO, logger="app"):
        for _ in range(2):
            await navegador.post("/api/analises", json={"texto": GOLPE_DE_PIX})

    assert _eventos(caplog, "cota_excedida") == [{"com_conta": True, "teto_global": False}]
    assert _valor("verifyscan_cota_excedida_total", com_conta="true") == antes + 1


async def test_print_barrado_pela_cota_tambem_conta(
    app: FastAPI, cliente: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    _cotas_de_producao(app, ia_cota_sem_conta=2)
    _ligar_ia(app, ClienteIAFalso())
    _ligar_leitura(app, ClienteLeituraFalso())

    with caplog.at_level(logging.INFO, logger="app"):
        resposta = await cliente.post("/api/analises/imagem", json=corpo_de_print())

    assert resposta.status_code == 429
    assert _eventos(caplog, "cota_excedida") == [{"com_conta": False, "teto_global": False}]


async def test_teto_global_entra_em_cota_excedida_com_o_campo(
    app: FastAPI,
    cliente: AsyncClient,
    uso: RepositorioUsoEmMemoria,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _cotas_de_producao(app, ia_teto_gasto_diario_usd=Decimal("0.0001"))
    _ligar_ia(app, ClienteIAFalso())

    with caplog.at_level(logging.INFO, logger="app"):
        await cliente.post("/api/analises", json={"texto": GOLPE_DE_PIX})
        await cliente.post("/api/analises", json={"texto": GOLPE_DE_PIX})

    assert _eventos(caplog, "cota_excedida") == [{"com_conta": False, "teto_global": True}]
    # Uma vez por dia, na análise que fez o gasto passar do teto.
    assert len(_eventos(caplog, "teto_global_atingido")) == 1


async def test_o_campo_teto_global_nao_muda_nenhuma_decisao_de_cota(
    uso: RepositorioUsoEmMemoria, relogio: RelogioFalso
) -> None:
    """A mesma sequência de reservas, comparada só pelo que decide: conceder e quanto resta."""
    cota = _servico(uso, relogio, teto_usd=Decimal("0.001"))
    dia = cota.hoje()

    decisoes = []
    for _ in range(6):
        situacao = await cota.reservar_ia(VISITANTE, False, 1, dia)
        decisoes.append((situacao.concedida, situacao.restantes, situacao.teto_global))
    await cota.registrar_gasto(_consumo(10_000, 0), dia, timeout_s=1)
    no_teto = await cota.reservar_ia("ip:outra", False, 1, dia)

    assert decisoes == [
        (True, 4, False),
        (True, 3, False),
        (True, 2, False),
        (True, 1, False),
        (True, 0, False),
        # A cota da pessoa acabou: não é o teto global.
        (False, 0, False),
    ]
    assert (no_teto.concedida, no_teto.restantes, no_teto.teto_global) == (False, 0, True)
    # Negada pelo teto, a reserva não gasta unidade de quem pediu (como antes).
    assert ("ia", "ip:outra", dia) not in uso.usos


async def test_o_gasto_do_dia_vai_para_a_metrica(
    uso: RepositorioUsoEmMemoria, relogio: RelogioFalso
) -> None:
    cota = _servico(uso, relogio)
    dia = cota.hoje()

    await cota.registrar_gasto(_consumo(1_000_000, 0), dia, timeout_s=1)

    assert _valor("verifyscan_gasto_ia_dolares_hoje") == pytest.approx(0.10)

    # No dia seguinte, a primeira reserva lê o gasto do dia novo: a métrica volta a zero.
    relogio.agora += timedelta(days=1)
    await cota.reservar_ia(VISITANTE, False, 1, cota.hoje())

    assert _valor("verifyscan_gasto_ia_dolares_hoje") == 0.0


# ─── login_falhou e cadastro_bloqueado ────────────────────────────────────────────────────


async def test_login_falhou_sem_o_email(
    cliente: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    await cliente.post("/api/auth/cadastro", json=CADASTRO)
    errada = {"email": LOGIN["email"], "senha": "senha errada demais"}

    with caplog.at_level(logging.INFO, logger="app"):
        for _ in range(11):
            await cliente.post("/api/auth/login", json=errada)

    falhas = _eventos(caplog, "login_falhou")
    assert falhas == [{"motivo": "credenciais"}] * 10 + [{"motivo": "limite"}]
    tudo = caplog.text + str([r.__dict__ for r in caplog.records])
    assert LOGIN["email"] not in tudo
    assert "senha errada demais" not in tudo


async def test_cadastro_bloqueado_sem_o_email(
    cliente: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="app"):
        for numero in range(6):
            await cliente.post(
                "/api/auth/cadastro", json={**CADASTRO, "email": f"pessoa{numero}@exemplo.com"}
            )

    assert _eventos(caplog, "cadastro_bloqueado") == [{}]
    assert "@exemplo.com" not in caplog.text + str([r.__dict__ for r in caplog.records])
