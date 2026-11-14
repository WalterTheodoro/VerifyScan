"""Proteção do login pela API (fatia 10, ADR-0024): tentativas de senha, cadastros por IP e o
Argon2 sem vaga.

O limitador de tentativas nasce em `criar_app()`, um por app: cada teste começa do zero.
"""

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import obter_hasher
from app.core.seguranca import HasherOcupado, HasherSenha
from tests.conftest import RelogioFalso
from tests.test_api_autenticacao import CADASTRO, LOGIN

MUITAS_TENTATIVAS = {"detail": "Muitas tentativas. Espere alguns minutos e tente de novo."}
CADASTROS_DEMAIS = {
    "detail": "Muitas contas foram criadas a partir desta conexão hoje. Tente de novo amanhã."
}
OCUPADO = {"detail": "Muitas pessoas estão entrando agora. Tente de novo em alguns segundos."}
ERRADA = {"email": LOGIN["email"], "senha": "senha errada demais"}


def _ip(numero: int) -> dict[str, str]:
    return {"x-forwarded-for": f"203.0.113.{numero}"}


class HasherContado(HasherSenha):
    """Conta as verificações: o limite precisa barrar ANTES do Argon2."""

    verificacoes = 0

    async def verificar(self, senha_hash: str, senha: str) -> bool:
        HasherContado.verificacoes += 1
        return await super().verificar(senha_hash, senha)


@pytest.fixture
async def navegador(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://teste") as cliente:
        yield cliente


async def _entrar(navegador: AsyncClient, corpo: dict[str, str], ip: int = 1) -> Any:
    return await navegador.post("/api/auth/login", json=corpo, headers=_ip(ip))


# ─── login ────────────────────────────────────────────────────────────────────────────────


async def test_dez_senhas_erradas_bloqueiam_a_conta_mesmo_com_a_senha_certa(
    app: FastAPI, navegador: AsyncClient
) -> None:
    await navegador.post("/api/auth/cadastro", json=CADASTRO)
    for tentativa in range(10):
        # IPs diferentes: é o limite da conta, não o do IP.
        assert (await _entrar(navegador, ERRADA, ip=tentativa)).status_code == 401

    hasher = HasherContado()
    app.dependency_overrides[obter_hasher] = lambda: hasher
    HasherContado.verificacoes = 0
    bloqueado = await _entrar(navegador, LOGIN, ip=99)

    assert bloqueado.status_code == 429
    assert bloqueado.json() == MUITAS_TENTATIVAS
    assert HasherContado.verificacoes == 0


async def test_email_sem_conta_e_bloqueado_igual(navegador: AsyncClient) -> None:
    """O 429 não pode revelar quem tem conta: o e-mail inexistente é limitado do mesmo jeito."""
    ninguem = {"email": "ninguem@exemplo.com", "senha": "qualquer senha"}
    for tentativa in range(10):
        assert (await _entrar(navegador, ninguem, ip=tentativa)).status_code == 401

    resposta = await _entrar(navegador, ninguem, ip=99)

    assert resposta.status_code == 429
    assert resposta.json() == MUITAS_TENTATIVAS


async def test_trinta_falhas_do_mesmo_ip_bloqueiam_o_ip(navegador: AsyncClient) -> None:
    for tentativa in range(30):
        corpo = {"email": f"pessoa{tentativa}@exemplo.com", "senha": "qualquer senha"}
        assert (await _entrar(navegador, corpo, ip=1)).status_code == 401

    mesmo_ip = await _entrar(navegador, {"email": "nova@exemplo.com", "senha": "x" * 8}, ip=1)
    outro_ip = await _entrar(navegador, {"email": "nova@exemplo.com", "senha": "x" * 8}, ip=2)

    assert mesmo_ip.status_code == 429
    assert outro_ip.status_code == 401


async def test_entrar_zera_as_falhas_da_conta(navegador: AsyncClient) -> None:
    await navegador.post("/api/auth/cadastro", json=CADASTRO)
    for tentativa in range(9):
        await _entrar(navegador, ERRADA, ip=tentativa)

    assert (await _entrar(navegador, LOGIN, ip=50)).status_code == 200

    for tentativa in range(9):
        assert (await _entrar(navegador, ERRADA, ip=tentativa)).status_code == 401


async def test_email_com_maiusculas_conta_como_o_mesmo(navegador: AsyncClient) -> None:
    for tentativa in range(10):
        corpo = {"email": "Maria@Exemplo.com " if tentativa % 2 else "maria@exemplo.com"}
        await _entrar(navegador, {**corpo, "senha": "errada errada"}, ip=tentativa)

    assert (await _entrar(navegador, ERRADA, ip=99)).status_code == 429


# ─── trocar senha e excluir ───────────────────────────────────────────────────────────────


async def test_troca_e_exclusao_somam_no_mesmo_limite_da_conta(navegador: AsyncClient) -> None:
    await navegador.post("/api/auth/cadastro", json=CADASTRO)
    errada = {"senha_atual": "não é a senha", "nova_senha": "outra senha boa"}
    for tentativa in range(5):
        resposta = await navegador.post("/api/conta/senha", json=errada, headers=_ip(tentativa))
        assert resposta.status_code == 400
    for tentativa in range(5):
        resposta = await navegador.post(
            "/api/conta/excluir", json={"senha": "não é a senha"}, headers=_ip(tentativa)
        )
        assert resposta.status_code == 400

    troca = await navegador.post(
        "/api/conta/senha",
        json={"senha_atual": CADASTRO["senha"], "nova_senha": "outra senha boa"},
        headers=_ip(99),
    )
    login = await _entrar(navegador, LOGIN, ip=98)

    assert troca.status_code == 429
    assert troca.json() == MUITAS_TENTATIVAS
    assert login.status_code == 429


# ─── cadastro ─────────────────────────────────────────────────────────────────────────────


async def test_cinco_cadastros_por_ip_por_dia(
    navegador: AsyncClient, relogio: RelogioFalso
) -> None:
    for numero in range(5):
        corpo = {**CADASTRO, "email": f"pessoa{numero}@exemplo.com"}
        resposta = await navegador.post("/api/auth/cadastro", json=corpo, headers=_ip(1))
        assert resposta.status_code == 201

    sexto = {**CADASTRO, "email": "sexta@exemplo.com"}
    mesmo_ip = await navegador.post("/api/auth/cadastro", json=sexto, headers=_ip(1))
    outro_ip = await navegador.post("/api/auth/cadastro", json=sexto, headers=_ip(2))

    assert mesmo_ip.status_code == 429
    assert mesmo_ip.json() == CADASTROS_DEMAIS
    assert outro_ip.status_code == 201

    relogio.agora += timedelta(days=1)
    corpo = {**CADASTRO, "email": "amanha@exemplo.com"}
    assert (
        await navegador.post("/api/auth/cadastro", json=corpo, headers=_ip(1))
    ).status_code == 201


async def test_cadastro_invalido_nao_gasta_a_cota_do_ip(navegador: AsyncClient) -> None:
    for _ in range(6):
        corpo = {**CADASTRO, "senha": "curta"}
        resposta = await navegador.post("/api/auth/cadastro", json=corpo, headers=_ip(1))
        assert resposta.status_code == 422

    assert (
        await navegador.post("/api/auth/cadastro", json=CADASTRO, headers=_ip(1))
    ).status_code == 201


# ─── Argon2 sem vaga ──────────────────────────────────────────────────────────────────────


async def test_argon2_sem_vaga_e_503_com_frase_propria(
    app: FastAPI, navegador: AsyncClient
) -> None:
    class HasherLotado(HasherSenha):
        async def verificar(self, senha_hash: str, senha: str) -> bool:
            raise HasherOcupado()

    hasher = HasherLotado()
    app.dependency_overrides[obter_hasher] = lambda: hasher

    resposta = await _entrar(navegador, LOGIN)

    assert resposta.status_code == 503
    assert resposta.json() == OCUPADO
