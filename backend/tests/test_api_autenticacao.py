"""Rotas /api/auth com repositórios em memória: status, mensagens em pt-BR e o cookie.

O fluxo de ponta a ponta contra o Postgres real está em
`tests/integracao/test_api_autenticacao.py`.
"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

from app.api.deps import obter_repositorio_sessoes, obter_usuario_atual
from app.core.config import get_settings
from app.services.repositorio_usuarios import UsuarioAutenticado
from tests.conftest import (
    RelogioFalso,
    RepositorioSessoesEmMemoria,
    RepositorioUsuariosEmMemoria,
    settings_de_teste,
)
from tests.test_api_analises import GOLPE_DE_PIX

CADASTRO = {"nome": "Maria", "email": "maria@exemplo.com", "senha": "uma senha boa"}
LOGIN = {"email": "maria@exemplo.com", "senha": "uma senha boa"}
SETE_DIAS_EM_SEGUNDOS = 7 * 24 * 60 * 60


@pytest.fixture
async def navegador(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Cliente que guarda cookie, em https: o httpx não devolve cookie Secure em http."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://teste") as cliente:
        yield cliente


def _cookie_de_sessao(resposta: Response) -> str:
    cabecalhos = [c for c in resposta.headers.get_list("set-cookie") if c.startswith("vs_sessao=")]
    assert len(cabecalhos) == 1, resposta.headers.get_list("set-cookie")
    return cabecalhos[0]


def _atributos(cabecalho: str) -> dict[str, str]:
    """`Set-Cookie` em dicionário, com os nomes de atributo em minúsculas."""
    _, *atributos = (parte.strip() for parte in cabecalho.split(";"))
    pares = (atributo.partition("=") for atributo in atributos)
    return {nome.lower(): valor for nome, _, valor in pares}


# ─── cadastro ─────────────────────────────────────────────────────────────────────────────


async def test_cadastro_devolve_201_com_nome_e_email(navegador: AsyncClient) -> None:
    resposta = await navegador.post("/api/auth/cadastro", json=CADASTRO)

    assert resposta.status_code == 201
    assert resposta.json() == {"nome": "Maria", "email": "maria@exemplo.com"}


async def test_cookie_tem_os_atributos_do_adr(navegador: AsyncClient) -> None:
    resposta = await navegador.post("/api/auth/cadastro", json=CADASTRO)

    atributos = _atributos(_cookie_de_sessao(resposta))
    assert "httponly" in atributos
    assert atributos["samesite"] == "lax"
    assert atributos["path"] == "/"
    assert atributos["max-age"] == str(SETE_DIAS_EM_SEGUNDOS)
    assert "secure" in atributos
    # Sem Domain: o cookie fica preso ao host que respondeu — o frontend, via proxy (fatia 3).
    assert "domain" not in atributos


async def test_cookie_sem_secure_quando_a_config_desliga(
    app: FastAPI, navegador: AsyncClient
) -> None:
    app.dependency_overrides[get_settings] = lambda: settings_de_teste(cookie_secure=False)

    resposta = await navegador.post("/api/auth/cadastro", json=CADASTRO)

    assert "secure" not in _atributos(_cookie_de_sessao(resposta))


async def test_max_age_segue_sessao_dias(app: FastAPI, navegador: AsyncClient) -> None:
    app.dependency_overrides[get_settings] = lambda: settings_de_teste(sessao_dias=1)

    resposta = await navegador.post("/api/auth/cadastro", json=CADASTRO)

    assert _atributos(_cookie_de_sessao(resposta))["max-age"] == "86400"


async def test_token_nao_aparece_no_corpo(navegador: AsyncClient) -> None:
    resposta = await navegador.post("/api/auth/cadastro", json=CADASTRO)

    token = _cookie_de_sessao(resposta).split(";")[0].removeprefix("vs_sessao=")
    assert token
    assert token not in resposta.text


async def test_email_duplicado_da_409(navegador: AsyncClient) -> None:
    await navegador.post("/api/auth/cadastro", json=CADASTRO)

    resposta = await navegador.post(
        "/api/auth/cadastro", json={**CADASTRO, "email": "MARIA@exemplo.com"}
    )

    assert resposta.status_code == 409
    assert resposta.json() == {"detail": "Já existe uma conta com este e-mail."}
    assert "set-cookie" not in resposta.headers


@pytest.mark.parametrize(
    ("corpo", "mensagem"),
    [
        ({"email": "maria@exemplo.com", "senha": "uma senha boa"}, "Informe como você"),
        ({"nome": "Maria", "senha": "uma senha boa"}, "Confira o e-mail"),
        ({"nome": "Maria", "email": "maria@exemplo.com"}, "pelo menos 8 caracteres"),
        ({**CADASTRO, "senha": "curta"}, "pelo menos 8 caracteres"),
    ],
)
async def test_cadastro_invalido_da_422_em_portugues(
    navegador: AsyncClient, corpo: dict[str, str], mensagem: str
) -> None:
    """Campo ausente cai na validação do service, não no 422 padrão em inglês."""
    resposta = await navegador.post("/api/auth/cadastro", json=corpo)

    assert resposta.status_code == 422
    assert isinstance(resposta.json()["detail"], str)
    assert mensagem in resposta.json()["detail"]


async def test_corpo_que_nao_e_json_e_recusado(
    navegador: AsyncClient, usuarios: RepositorioUsuariosEmMemoria
) -> None:
    """Parte da defesa de CSRF (ADR-0013): formulário cross-site não manda Content-Type JSON
    sem preflight de CORS."""
    resposta = await navegador.post(
        "/api/auth/cadastro",
        content=json.dumps(CADASTRO),
        headers={"Content-Type": "text/plain"},
    )

    assert resposta.status_code == 422
    assert usuarios.credenciais == {}


# ─── login ────────────────────────────────────────────────────────────────────────────────


async def test_login_certo_da_200_e_cookie(app: FastAPI, navegador: AsyncClient) -> None:
    await navegador.post("/api/auth/cadastro", json=CADASTRO)
    navegador.cookies.clear()

    resposta = await navegador.post("/api/auth/login", json=LOGIN)

    assert resposta.status_code == 200
    assert resposta.json() == {"nome": "Maria", "email": "maria@exemplo.com"}
    assert "httponly" in _atributos(_cookie_de_sessao(resposta))


@pytest.mark.parametrize(
    "corpo",
    [
        {"email": "maria@exemplo.com", "senha": "senha errada"},
        {"email": "ninguem@exemplo.com", "senha": "uma senha boa"},
        {},
    ],
)
async def test_login_errado_da_401_com_a_mesma_mensagem(
    navegador: AsyncClient, corpo: dict[str, str]
) -> None:
    await navegador.post("/api/auth/cadastro", json=CADASTRO)
    navegador.cookies.clear()

    resposta = await navegador.post("/api/auth/login", json=corpo)

    assert resposta.status_code == 401
    assert resposta.json() == {"detail": "E-mail ou senha incorretos."}
    assert "set-cookie" not in resposta.headers


# ─── /eu e logout ─────────────────────────────────────────────────────────────────────────


async def test_eu_sem_cookie_da_401(navegador: AsyncClient) -> None:
    resposta = await navegador.get("/api/auth/eu")

    assert resposta.status_code == 401
    assert resposta.json() == {"detail": "Você precisa entrar na sua conta."}


async def test_cadastro_eu_logout_eu(navegador: AsyncClient) -> None:
    await navegador.post("/api/auth/cadastro", json=CADASTRO)

    eu = await navegador.get("/api/auth/eu")
    assert eu.status_code == 200
    assert eu.json() == {"nome": "Maria", "email": "maria@exemplo.com"}

    saida = await navegador.post("/api/auth/logout")
    assert saida.status_code == 204
    assert _atributos(_cookie_de_sessao(saida))["max-age"] == "0"

    assert (await navegador.get("/api/auth/eu")).status_code == 401


async def test_cookie_antigo_nao_vale_depois_do_logout(
    navegador: AsyncClient, sessoes: RepositorioSessoesEmMemoria
) -> None:
    """Logout apaga a sessão no servidor, não só o cookie do navegador."""
    await navegador.post("/api/auth/cadastro", json=CADASTRO)
    token = navegador.cookies["vs_sessao"]

    await navegador.post("/api/auth/logout")

    assert sessoes.sessoes == []
    navegador.cookies.set("vs_sessao", token)
    assert (await navegador.get("/api/auth/eu")).status_code == 401


async def test_logout_sem_cookie_da_204_e_limpa_mesmo_assim(navegador: AsyncClient) -> None:
    resposta = await navegador.post("/api/auth/logout")

    assert resposta.status_code == 204
    assert _atributos(_cookie_de_sessao(resposta))["max-age"] == "0"


async def test_sessao_vencida_da_401(navegador: AsyncClient, relogio: RelogioFalso) -> None:
    await navegador.post("/api/auth/cadastro", json=CADASTRO)
    relogio.agora += timedelta(days=7)

    assert (await navegador.get("/api/auth/eu")).status_code == 401


async def test_obter_usuario_atual_e_substituivel(app: FastAPI, navegador: AsyncClient) -> None:
    """As rotas protegidas das próximas fatias testam sem montar sessão."""
    app.dependency_overrides[obter_usuario_atual] = lambda: UsuarioAutenticado(
        id=uuid.uuid4(), nome="Fixa", email="fixa@exemplo.com"
    )

    resposta = await navegador.get("/api/auth/eu")

    assert resposta.json() == {"nome": "Fixa", "email": "fixa@exemplo.com"}


# ─── banco lento ──────────────────────────────────────────────────────────────────────────


class RepositorioSessoesLento(RepositorioSessoesEmMemoria):
    async def buscar_usuario(self, token_hash: str) -> UsuarioAutenticado | None:
        await asyncio.sleep(3600)
        raise AssertionError("o timeout deveria ter cortado antes")

    async def apagar(self, token_hash: str) -> None:
        await asyncio.sleep(3600)


@pytest.fixture
def banco_lento(app: FastAPI, relogio: RelogioFalso) -> None:
    app.dependency_overrides[obter_repositorio_sessoes] = lambda: RepositorioSessoesLento(relogio)
    app.dependency_overrides[get_settings] = lambda: settings_de_teste(timeout_autenticacao_s=0.05)


MENSAGEM_503 = {"detail": "O serviço está iniciando. Tente de novo em alguns segundos."}


@pytest.mark.usefixtures("banco_lento")
async def test_banco_lento_da_503_em_portugues(navegador: AsyncClient) -> None:
    navegador.cookies.set("vs_sessao", "qualquer")

    resposta = await navegador.get("/api/auth/eu")

    assert resposta.status_code == 503
    assert resposta.json() == MENSAGEM_503


@pytest.mark.usefixtures("banco_lento")
async def test_logout_com_banco_lento_da_503_e_limpa_o_cookie(navegador: AsyncClient) -> None:
    navegador.cookies.set("vs_sessao", "qualquer")

    resposta = await navegador.post("/api/auth/logout")

    assert resposta.status_code == 503
    assert resposta.json() == MENSAGEM_503
    assert _atributos(_cookie_de_sessao(resposta))["max-age"] == "0"


# ─── análise anônima continua igual ───────────────────────────────────────────────────────


async def test_analise_continua_funcionando_sem_cookie(navegador: AsyncClient) -> None:
    resposta = await navegador.post("/api/analises", json={"texto": GOLPE_DE_PIX})

    assert resposta.status_code == 200
    assert resposta.json()["nivel_risco"] == "ALTO"
    assert "vs_sessao" not in navegador.cookies


# ─── contrato no OpenAPI ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("metodo", "caminho", "esperados"),
    [
        ("post", "/api/auth/cadastro", {"409", "422", "503"}),
        ("post", "/api/auth/login", {"401", "422", "503"}),
        ("post", "/api/auth/logout", {"503"}),
        ("get", "/api/auth/eu", {"401", "503"}),
    ],
)
def test_openapi_declara_os_erros_de_cada_rota(
    app: FastAPI, metodo: str, caminho: str, esperados: set[str]
) -> None:
    """O frontend trata cada um destes; sem declaração, o Swagger os mostra "Undocumented"."""
    respostas = app.openapi()["paths"][caminho][metodo]["responses"]

    for codigo in esperados:
        assert codigo in respostas, f"{metodo.upper()} {caminho} não declara {codigo}"
        assert "`detail`" in respostas[codigo]["description"]
