"""Cota diária da IA e teto de gasto, de ponta a ponta pela API (fatia 10, ADR-0024).

Repositório de uso em memória e clientes de IA falsos: nada aqui fala com banco nem com a rede. Os
valores de cota são os de produção (5 sem conta, 25 com conta), passados explicitamente: o
`settings_de_teste` padrão deixa a cota no teto para os outros testes.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    obter_analisador_ia,
    obter_consumo,
    obter_leitor_de_print,
    obter_repositorio_sessoes,
    obter_repositorio_uso,
)
from app.core.config import get_settings
from app.formulator.analisador import AnalisadorIA
from app.formulator.cliente import ConsumoDaIA
from app.ocr.leitura import LeitorDePrint
from app.services.cota import COTA_DE_PRINT, COTA_DE_TEXTO
from app.services.orquestrador import LEITURA_INDISPONIVEL
from app.services.repositorio_sessoes import RepositorioSessoes
from app.services.repositorio_usuarios import UsuarioAutenticado
from tests.conftest import (
    ClienteIAFalso,
    ClienteLeituraFalso,
    RelogioFalso,
    RepositorioSessoesEmMemoria,
    RepositorioUsoEmMemoria,
    corpo_de_print,
    saida_da_leitura,
    settings_de_teste,
)
from tests.test_api_analises import GOLPE_DE_PIX

COM_CONTA = "Com uma conta, são 25 por dia."
CADASTRO = {"nome": "Maria", "email": "maria@exemplo.com", "senha": "senha-forte-123"}


def _cotas_de_producao(app: FastAPI, **mudancas: object) -> None:
    valores: dict[str, object] = {"ia_cota_sem_conta": 5, "ia_cota_com_conta": 25}
    valores.update(mudancas)
    app.dependency_overrides[get_settings] = lambda: settings_de_teste(**valores)


# Fora do default do argumento (B008); o FastAPI lê o mesmo `Depends` de qualquer lugar.
_CONSUMO = Depends(obter_consumo)


def _ligar_ia(app: FastAPI, cliente: ClienteIAFalso, timeout_s: float = 15) -> ClienteIAFalso:
    """Como a dependência real: o analisador recebe o `ConsumoDaIA` da requisição."""

    def analisador(consumo: ConsumoDaIA = _CONSUMO) -> AnalisadorIA:
        return AnalisadorIA(cliente, timeout_s, consumo)

    app.dependency_overrides[obter_analisador_ia] = analisador
    return cliente


def _ligar_leitura(app: FastAPI, cliente: ClienteLeituraFalso) -> ClienteLeituraFalso:
    def leitor(consumo: ConsumoDaIA = _CONSUMO) -> LeitorDePrint:
        return LeitorDePrint(cliente, 10, consumo)

    app.dependency_overrides[obter_leitor_de_print] = leitor
    return cliente


async def _texto(cliente: AsyncClient, texto: str = GOLPE_DE_PIX, **kwargs: Any) -> Any:
    resposta = await cliente.post("/api/analises", json={"texto": texto}, **kwargs)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


@pytest.fixture
async def navegador(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """HTTPS, para o cookie Secure da sessão voltar nos pedidos seguintes."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://teste") as cliente:
        yield cliente


# ── Texto ────────────────────────────────────────────────────────────────────────────────────


async def test_texto_sem_conta_tem_5_com_ia_e_depois_so_o_motor_com_o_aviso(
    app: FastAPI, cliente: AsyncClient
) -> None:
    _cotas_de_producao(app)
    ia = _ligar_ia(app, ClienteIAFalso())

    corpos = [await _texto(cliente) for _ in range(6)]

    assert len(ia.chamadas) == 5
    assert [c["ia_restantes_hoje"] for c in corpos] == [4, 3, 2, 1, 0, 0]
    assert all(c["motivo_sem_ia"] is None for c in corpos[:5])
    ultimo = corpos[5]
    assert ultimo["explicacao_indisponivel"] is True
    assert ultimo["explicacao_ia"] is None
    assert ultimo["nivel_ia"] is None
    assert ultimo["nivel_risco"] == ultimo["nivel_motor"] == "ALTO"
    assert ultimo["motivo_sem_ia"] == "cota"
    assert ultimo["aviso_sem_ia"] == f"{COTA_DE_TEXTO} {COM_CONTA}"


async def test_com_conta_o_aviso_nao_oferece_conta(app: FastAPI, navegador: AsyncClient) -> None:
    _cotas_de_producao(app, ia_cota_com_conta=2)
    _ligar_ia(app, ClienteIAFalso())
    assert (await navegador.post("/api/auth/cadastro", json=CADASTRO)).status_code == 201

    corpos = [await _texto(navegador) for _ in range(3)]

    assert [c["ia_restantes_hoje"] for c in corpos] == [1, 0, 0]
    assert corpos[2]["motivo_sem_ia"] == "cota"
    assert corpos[2]["aviso_sem_ia"] == COTA_DE_TEXTO


async def test_conta_e_visitante_no_mesmo_ip_tem_cotas_separadas(
    app: FastAPI, cliente: AsyncClient, navegador: AsyncClient
) -> None:
    _cotas_de_producao(app)
    _ligar_ia(app, ClienteIAFalso())
    for _ in range(5):
        await _texto(cliente)
    await navegador.post("/api/auth/cadastro", json=CADASTRO)

    assert (await _texto(navegador))["ia_restantes_hoje"] == 24


async def test_entrada_invalida_nao_gasta_unidade(
    app: FastAPI, cliente: AsyncClient, uso: RepositorioUsoEmMemoria
) -> None:
    _cotas_de_producao(app)
    _ligar_ia(app, ClienteIAFalso())

    resposta = await cliente.post("/api/analises", json={"texto": "!!! ???"})

    assert resposta.status_code == 422
    assert uso.usos == {}


async def test_ia_desligada_nao_confere_cota(
    app: FastAPI, cliente: AsyncClient, uso: RepositorioUsoEmMemoria
) -> None:
    _cotas_de_producao(app)

    corpo = await _texto(cliente)

    assert corpo["ia_restantes_hoje"] is None
    assert corpo["motivo_sem_ia"] is None
    assert uso.usos == {}


class UsoForaDoAr(RepositorioUsoEmMemoria):
    async def gasto_do_dia(self, dia: date) -> Decimal:
        raise ConnectionError("banco fora")


class UsoLento(RepositorioUsoEmMemoria):
    async def gasto_do_dia(self, dia: date) -> Decimal:
        await asyncio.sleep(3600)
        raise AssertionError("o teto da cota deveria ter cortado antes")


@pytest.mark.parametrize("repositorio", [UsoForaDoAr, UsoLento])
async def test_cota_que_nao_responde_deixa_o_texto_so_com_o_motor_sem_frase_de_cota(
    app: FastAPI,
    cliente: AsyncClient,
    repositorio: type[RepositorioUsoEmMemoria],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Fail-closed para o dinheiro, mas a pessoa recebe a análise: é o plano B comum, e não a
    frase de cota, que seria falsa."""
    _cotas_de_producao(app, timeout_cota_s=0.05)
    app.dependency_overrides[obter_repositorio_uso] = repositorio
    ia = _ligar_ia(app, ClienteIAFalso())

    with caplog.at_level(logging.WARNING, logger="app"):
        corpo = await _texto(cliente)

    assert ia.chamadas == []
    assert corpo["explicacao_indisponivel"] is True
    assert corpo["motivo_sem_ia"] is None
    assert corpo["aviso_sem_ia"] is None
    assert corpo["ia_restantes_hoje"] is None
    assert "Cota da IA não conferida" in caplog.text


async def test_teto_global_atingido_deixa_todos_sem_ia_com_a_frase_de_cota(
    app: FastAPI, cliente: AsyncClient, uso: RepositorioUsoEmMemoria, relogio: RelogioFalso
) -> None:
    _cotas_de_producao(app, ia_teto_gasto_diario_usd=Decimal("0.5"))
    ia = _ligar_ia(app, ClienteIAFalso())
    from app.core.relogio import dia_de_sao_paulo
    from app.services.repositorio_uso import GastoDaChamada

    await uso.somar_gasto(dia_de_sao_paulo(relogio()), GastoDaChamada(0, 0, Decimal("0.5"), 1, 0))

    corpo = await _texto(cliente)

    assert ia.chamadas == []
    assert corpo["motivo_sem_ia"] == "cota"
    assert corpo["ia_restantes_hoje"] == 0
    assert corpo["aviso_sem_ia"] == f"{COTA_DE_TEXTO} {COM_CONTA}"


async def test_o_dono_e_resolvido_uma_vez_so(
    app: FastAPI,
    navegador: AsyncClient,
    relogio: RelogioFalso,
    sessoes: RepositorioSessoesEmMemoria,
) -> None:
    """A janela da cota resolve a sessão, e o registro reaproveita o dono (ADR-0024)."""

    class SessoesContadas(RepositorioSessoesEmMemoria):
        consultas = 0

        async def buscar_usuario(self, token_hash: str) -> UsuarioAutenticado | None:
            SessoesContadas.consultas += 1
            return await sessoes.buscar_usuario(token_hash)

    _cotas_de_producao(app)
    _ligar_ia(app, ClienteIAFalso())
    await navegador.post("/api/auth/cadastro", json=CADASTRO)
    contadas: RepositorioSessoes = SessoesContadas(relogio)
    app.dependency_overrides[obter_repositorio_sessoes] = lambda: contadas

    corpo = await _texto(navegador)

    assert corpo["salva_no_historico"] is True
    assert SessoesContadas.consultas == 1


# ── Print ────────────────────────────────────────────────────────────────────────────────────


async def test_print_gasta_3_e_o_segundo_e_recusado_com_429(
    app: FastAPI, cliente: AsyncClient
) -> None:
    _cotas_de_producao(app)
    _ligar_ia(app, ClienteIAFalso())
    leitura = _ligar_leitura(app, ClienteLeituraFalso())

    primeiro = await cliente.post("/api/analises/imagem", json=corpo_de_print())
    segundo = await cliente.post("/api/analises/imagem", json=corpo_de_print())
    texto = await _texto(cliente)

    assert primeiro.status_code == 200
    assert primeiro.json()["ia_restantes_hoje"] == 2
    assert segundo.status_code == 429
    assert segundo.json() == {"detail": COTA_DE_PRINT}
    assert len(leitura.chamadas) == 1  # sem cota, sem leitura
    assert texto["ia_restantes_hoje"] == 1
    assert texto["motivo_sem_ia"] is None


async def test_print_com_a_cota_fora_do_ar_e_503_com_a_frase_honesta(
    app: FastAPI, cliente: AsyncClient
) -> None:
    _cotas_de_producao(app)
    app.dependency_overrides[obter_repositorio_uso] = UsoForaDoAr
    _ligar_ia(app, ClienteIAFalso())
    leitura = _ligar_leitura(app, ClienteLeituraFalso())

    resposta = await cliente.post("/api/analises/imagem", json=corpo_de_print())

    assert resposta.status_code == 503
    assert resposta.json() == {"detail": LEITURA_INDISPONIVEL}
    assert leitura.chamadas == []


async def test_imagem_invalida_nao_gasta_unidade(
    app: FastAPI, cliente: AsyncClient, uso: RepositorioUsoEmMemoria
) -> None:
    _cotas_de_producao(app)
    _ligar_ia(app, ClienteIAFalso())
    _ligar_leitura(app, ClienteLeituraFalso())

    resposta = await cliente.post("/api/analises/imagem", json=corpo_de_print(b"nao e imagem"))

    assert resposta.status_code == 422
    assert uso.usos == {}


# ── Gasto ────────────────────────────────────────────────────────────────────────────────────


def _gasto_de_hoje(uso: RepositorioUsoEmMemoria) -> Any:
    (gasto,) = uso.gastos.values()
    return gasto


async def test_o_gasto_soma_o_usage_da_resposta(
    app: FastAPI, cliente: AsyncClient, uso: RepositorioUsoEmMemoria
) -> None:
    _cotas_de_producao(app)
    _ligar_ia(app, ClienteIAFalso())

    await _texto(cliente)

    gasto = _gasto_de_hoje(uso)
    # 1000 x 0,10/M + 200 x 0,50/M
    assert (gasto.tokens_entrada, gasto.tokens_saida, gasto.chamadas) == (1000, 200, 1)
    assert gasto.custo_usd == Decimal("0.0002")


async def test_resposta_invalida_da_ia_tambem_entra_no_gasto(
    app: FastAPI, cliente: AsyncClient, uso: RepositorioUsoEmMemoria
) -> None:
    """Plano B por JSON inválido: a chamada foi cobrada do mesmo jeito."""
    _cotas_de_producao(app)
    _ligar_ia(app, ClienteIAFalso("isto não é JSON"))

    corpo = await _texto(cliente)

    assert corpo["explicacao_indisponivel"] is True
    assert corpo["motivo_sem_ia"] is None
    assert _gasto_de_hoje(uso).chamadas == 1


async def test_timeout_da_ia_e_contado_fora_do_custo(
    app: FastAPI, cliente: AsyncClient, uso: RepositorioUsoEmMemoria
) -> None:
    _cotas_de_producao(app)
    _ligar_ia(app, ClienteIAFalso(demora_s=1), timeout_s=0.05)

    await _texto(cliente)

    gasto = _gasto_de_hoje(uso)
    assert gasto.chamadas_com_timeout == 1
    assert gasto.chamadas == 0
    assert gasto.custo_usd == 0


async def test_print_soma_a_leitura_e_a_analise(
    app: FastAPI, cliente: AsyncClient, uso: RepositorioUsoEmMemoria
) -> None:
    _cotas_de_producao(app)
    _ligar_ia(app, ClienteIAFalso())
    _ligar_leitura(app, ClienteLeituraFalso())

    assert (await cliente.post("/api/analises/imagem", json=corpo_de_print())).status_code == 200

    gasto = _gasto_de_hoje(uso)
    assert (gasto.tokens_entrada, gasto.tokens_saida, gasto.chamadas) == (5500, 500, 2)


async def test_leitura_que_falha_tambem_entra_no_gasto(
    app: FastAPI, cliente: AsyncClient, uso: RepositorioUsoEmMemoria
) -> None:
    """Print ilegível: 422 para a pessoa, mas a leitura foi cobrada e as unidades não voltam."""
    _cotas_de_producao(app)
    _ligar_ia(app, ClienteIAFalso())
    _ligar_leitura(app, ClienteLeituraFalso(saida_da_leitura(legivel="nao")))

    resposta = await cliente.post("/api/analises/imagem", json=corpo_de_print())

    assert resposta.status_code == 422
    gasto = _gasto_de_hoje(uso)
    assert (gasto.tokens_entrada, gasto.chamadas) == (4500, 1)
    (usadas,) = uso.usos.values()
    assert usadas == 3


# ── IP ───────────────────────────────────────────────────────────────────────────────────────


async def test_cada_ip_tem_a_propria_cota(app: FastAPI, cliente: AsyncClient) -> None:
    _cotas_de_producao(app)
    _ligar_ia(app, ClienteIAFalso())
    um = {"x-forwarded-for": "203.0.113.1"}
    for _ in range(5):
        await _texto(cliente, headers=um)

    esgotado = await _texto(cliente, headers=um)
    outro = await _texto(cliente, headers={"x-forwarded-for": "203.0.113.2"})

    assert esgotado["motivo_sem_ia"] == "cota"
    assert outro["ia_restantes_hoje"] == 4


async def test_ip_repassado_sem_o_segredo_nao_troca_a_cota(
    app: FastAPI, cliente: AsyncClient
) -> None:
    """Forjar o `X-VerifyScan-IP` sem o segredo não dá cota nova: o cabeçalho é ignorado."""
    _cotas_de_producao(app)
    _ligar_ia(app, ClienteIAFalso())
    for _ in range(5):
        await _texto(cliente)

    forjado = await _texto(
        cliente, headers={"x-verifyscan-ip": "198.51.100.9", "x-verifyscan-segredo": "chute"}
    )

    assert forjado["motivo_sem_ia"] == "cota"


async def test_ip_repassado_com_o_segredo_e_a_chave_da_cota(
    app: FastAPI, cliente: AsyncClient
) -> None:
    _cotas_de_producao(app)
    _ligar_ia(app, ClienteIAFalso())
    segredo = settings_de_teste().proxy_segredo.get_secret_value()
    for _ in range(5):
        await _texto(cliente)

    pelo_proxy = await _texto(
        cliente, headers={"x-verifyscan-ip": "198.51.100.9", "x-verifyscan-segredo": segredo}
    )

    assert pelo_proxy["ia_restantes_hoje"] == 4
