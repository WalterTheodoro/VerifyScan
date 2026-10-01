"""Rotas do histórico e de /api/conta com repositórios em memória (ADR-0015).

Aqui se confere o HTTP: status, `detail` em pt-BR, formato do corpo e a desvinculação que nunca
derruba a listagem. O SQL — janela, dono, CASCADE — é provado contra o Postgres em
`tests/integracao/test_historico.py`.
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import obter_repositorio_historico, obter_usuario_atual
from app.core.config import get_settings
from app.services.repositorio_historico import AnaliseDoHistorico, FatorDoHistorico
from app.services.repositorio_usuarios import UsuarioAutenticado
from tests.conftest import RelogioFalso, RepositorioHistoricoEmMemoria, settings_de_teste

MARIA = UsuarioAutenticado(id=uuid.uuid4(), nome="Maria", email="maria@exemplo.com")
JOAO = UsuarioAutenticado(id=uuid.uuid4(), nome="João", email="joao@exemplo.com")
SEGREDO = "XYZZY4242"


@pytest.fixture
async def navegador(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://teste") as cliente:
        yield cliente


@pytest.fixture
def como_maria(app: FastAPI) -> None:
    app.dependency_overrides[obter_usuario_atual] = lambda: MARIA


def _analise(relogio: RelogioFalso, horas_atras: float = 1) -> AnaliseDoHistorico:
    return AnaliseDoHistorico(
        id=uuid.uuid4(),
        criada_em=relogio() - timedelta(hours=horas_atras),
        nivel_risco="MEDIO",
        score=40,
        fatores=(
            FatorDoHistorico(categoria="ameaca_bloqueio", descricao="Ameaça bloquear.", peso=15),
            FatorDoHistorico(categoria="urgencia", descricao="Pede pressa.", peso=10),
        ),
    )


# ─── GET /api/historico ───────────────────────────────────────────────────────────────────


@pytest.mark.usefixtures("como_maria")
async def test_lista_as_da_conta_no_formato_do_contrato(
    navegador: AsyncClient, historico: RepositorioHistoricoEmMemoria, relogio: RelogioFalso
) -> None:
    analise = _analise(relogio)
    historico.adicionar(MARIA.id, analise)
    historico.adicionar(JOAO.id, _analise(relogio))

    resposta = await navegador.get("/api/historico")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["dias"] == 7
    assert len(corpo["analises"]) == 1
    item = corpo["analises"][0]
    assert item["id"] == str(analise.id)
    assert item["nivel_risco"] == "MEDIO"
    assert item["score_risco"] == 40
    assert item["fatores"] == [
        {"categoria": "ameaca_bloqueio", "descricao": "Ameaça bloquear.", "peso": 15},
        {"categoria": "urgencia", "descricao": "Pede pressa.", "peso": 10},
    ]
    # ISO 8601 com fuso: a tela converte para America/Sao_Paulo sem adivinhar.
    assert item["created_at"].endswith(("Z", "+00:00"))


@pytest.mark.usefixtures("como_maria")
async def test_a_janela_segue_historico_dias(
    app: FastAPI,
    navegador: AsyncClient,
    historico: RepositorioHistoricoEmMemoria,
    relogio: RelogioFalso,
) -> None:
    app.dependency_overrides[get_settings] = lambda: settings_de_teste(historico_dias=1)
    historico.adicionar(MARIA.id, _analise(relogio, horas_atras=2))
    historico.adicionar(MARIA.id, _analise(relogio, horas_atras=25))

    corpo = (await navegador.get("/api/historico")).json()

    assert corpo["dias"] == 1
    assert len(corpo["analises"]) == 1


@pytest.mark.usefixtures("como_maria")
async def test_listar_tambem_desvincula_as_vencidas(
    navegador: AsyncClient, historico: RepositorioHistoricoEmMemoria, relogio: RelogioFalso
) -> None:
    historico.adicionar(MARIA.id, _analise(relogio, horas_atras=8 * 24))

    await navegador.get("/api/historico")

    assert historico.desvinculacoes == 1
    assert historico.linhas[0].dono is None


class HistoricoQueNaoDesvincula(RepositorioHistoricoEmMemoria):
    async def desvincular_vencidas(self, janela: timedelta) -> int:
        raise RuntimeError(f"falhou {SEGREDO}")


@pytest.mark.usefixtures("como_maria")
async def test_desvinculacao_que_falha_so_loga_e_a_listagem_continua(
    app: FastAPI,
    navegador: AsyncClient,
    relogio: RelogioFalso,
    caplog: pytest.LogCaptureFixture,
) -> None:
    falho = HistoricoQueNaoDesvincula(relogio)
    falho.adicionar(MARIA.id, _analise(relogio))
    falho.adicionar(MARIA.id, _analise(relogio, horas_atras=8 * 24))
    app.dependency_overrides[obter_repositorio_historico] = lambda: falho

    with caplog.at_level(logging.WARNING):
        resposta = await navegador.get("/api/historico")

    assert resposta.status_code == 200
    # A vencida continua ligada no "banco", mas a leitura nunca a mostra.
    assert len(resposta.json()["analises"]) == 1
    assert "RuntimeError" in caplog.text
    assert SEGREDO not in caplog.text


class HistoricoLento(RepositorioHistoricoEmMemoria):
    async def listar(
        self, usuario_id: uuid.UUID, janela: timedelta, limite: int
    ) -> list[AnaliseDoHistorico]:
        await asyncio.sleep(3600)
        raise AssertionError("o timeout deveria ter cortado antes")


@pytest.mark.usefixtures("como_maria")
async def test_banco_lento_da_503_em_portugues(
    app: FastAPI, navegador: AsyncClient, relogio: RelogioFalso
) -> None:
    app.dependency_overrides[obter_repositorio_historico] = lambda: HistoricoLento(relogio)
    app.dependency_overrides[get_settings] = lambda: settings_de_teste(
        timeout_autenticacao_s=0.05, timeout_persistencia_s=0.05
    )

    resposta = await navegador.get("/api/historico")

    assert resposta.status_code == 503
    assert resposta.json() == {
        "detail": "O serviço está iniciando. Tente de novo em alguns segundos."
    }


# ─── DELETE ───────────────────────────────────────────────────────────────────────────────

NAO_ENCONTRADA = {"detail": "Não encontramos esta análise."}


@pytest.mark.usefixtures("como_maria")
async def test_apagar_uma_da_204_e_ela_some(
    navegador: AsyncClient, historico: RepositorioHistoricoEmMemoria, relogio: RelogioFalso
) -> None:
    analise = _analise(relogio)
    historico.adicionar(MARIA.id, analise)

    resposta = await navegador.delete(f"/api/historico/{analise.id}")

    assert resposta.status_code == 204
    assert historico.linhas == []


@pytest.mark.usefixtures("como_maria")
@pytest.mark.parametrize("caso", ["de outra pessoa", "inexistente", "id malformado"])
async def test_apagar_o_que_nao_e_seu_da_o_mesmo_404(
    navegador: AsyncClient,
    historico: RepositorioHistoricoEmMemoria,
    relogio: RelogioFalso,
    caso: str,
) -> None:
    """Não revelar existência: dono errado, id que não existe e id inválido respondem igual."""
    do_joao = _analise(relogio)
    historico.adicionar(JOAO.id, do_joao)
    alvo = {
        "de outra pessoa": str(do_joao.id),
        "inexistente": str(uuid.uuid4()),
        "id malformado": "nao-e-um-uuid",
    }[caso]

    resposta = await navegador.delete(f"/api/historico/{alvo}")

    assert resposta.status_code == 404
    assert resposta.json() == NAO_ENCONTRADA
    assert len(historico.linhas) == 1


@pytest.mark.usefixtures("como_maria")
async def test_apagar_todas_so_apaga_as_da_conta(
    navegador: AsyncClient, historico: RepositorioHistoricoEmMemoria, relogio: RelogioFalso
) -> None:
    historico.adicionar(MARIA.id, _analise(relogio))
    historico.adicionar(MARIA.id, _analise(relogio))
    historico.adicionar(JOAO.id, _analise(relogio))

    resposta = await navegador.delete("/api/historico")

    assert resposta.status_code == 204
    assert [linha.dono for linha in historico.linhas] == [JOAO.id]


# ─── GET /api/conta ───────────────────────────────────────────────────────────────────────


async def test_conta_devolve_nome_email_e_data_de_criacao(navegador: AsyncClient) -> None:
    await navegador.post(
        "/api/auth/cadastro",
        json={"nome": "Maria", "email": "maria@exemplo.com", "senha": "uma senha boa"},
    )

    resposta = await navegador.get("/api/conta")

    assert resposta.status_code == 200
    assert resposta.json() == {
        "nome": "Maria",
        "email": "maria@exemplo.com",
        "criado_em": "2026-10-01T12:00:00Z",
    }


# ─── sem sessão e OpenAPI ─────────────────────────────────────────────────────────────────

ROTAS = [
    ("get", "/api/historico"),
    ("delete", f"/api/historico/{uuid.uuid4()}"),
    ("delete", "/api/historico"),
    ("get", "/api/conta"),
]


@pytest.mark.parametrize(("metodo", "caminho"), ROTAS)
async def test_sem_sessao_da_401(navegador: AsyncClient, metodo: str, caminho: str) -> None:
    resposta = await navegador.request(metodo.upper(), caminho)

    assert resposta.status_code == 401
    assert resposta.json() == {"detail": "Você precisa entrar na sua conta."}


@pytest.mark.parametrize(
    ("metodo", "caminho", "esperados"),
    [
        ("get", "/api/historico", {"401", "503"}),
        ("delete", "/api/historico/{analise_id}", {"401", "404", "503"}),
        ("delete", "/api/historico", {"401", "503"}),
        ("get", "/api/conta", {"401", "503"}),
    ],
)
def test_openapi_declara_os_erros_de_cada_rota(
    app: FastAPI, metodo: str, caminho: str, esperados: set[str]
) -> None:
    respostas = app.openapi()["paths"][caminho][metodo]["responses"]

    for codigo in esperados:
        assert codigo in respostas, f"{metodo.upper()} {caminho} não declara {codigo}"
        assert "`detail`" in respostas[codigo]["description"]
