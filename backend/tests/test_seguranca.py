"""Hasher de senha: Argon2id com os parâmetros mínimos da OWASP (ADR-0013)."""

import pytest
from argon2 import PasswordHasher

from app.core.seguranca import HasherSenha


@pytest.fixture(scope="module")
def hasher() -> HasherSenha:
    return HasherSenha()


async def test_hash_usa_argon2id_com_os_parametros_da_owasp(hasher: HasherSenha) -> None:
    """Os defaults do argon2-cffi (64 MiB, p=4) não cabem no Render gratuito."""
    senha_hash = await hasher.gerar("uma senha qualquer")

    assert senha_hash.startswith("$argon2id$v=19$m=19456,t=2,p=1$")


async def test_verifica_a_senha_certa_e_recusa_a_errada(hasher: HasherSenha) -> None:
    senha_hash = await hasher.gerar("senha certa")

    assert await hasher.verificar(senha_hash, "senha certa") is True
    assert await hasher.verificar(senha_hash, "senha errada") is False


async def test_senha_nao_sofre_strip(hasher: HasherSenha) -> None:
    senha_hash = await hasher.gerar(" com espaços ")

    assert await hasher.verificar(senha_hash, "com espaços") is False


async def test_hash_corrompido_e_recusa_e_nao_excecao(hasher: HasherSenha) -> None:
    assert await hasher.verificar("isto não é um hash", "qualquer") is False


async def test_hash_com_outros_parametros_precisa_de_rehash(hasher: HasherSenha) -> None:
    antigo = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash("x")
    atual = await hasher.gerar("x")

    assert hasher.precisa_rehash(antigo) is True
    assert hasher.precisa_rehash(atual) is False


async def test_verificar_contra_falso_nao_levanta(hasher: HasherSenha) -> None:
    """O hash de mentira existe só para gastar o mesmo tempo quando a conta não existe."""
    await hasher.verificar_contra_falso("qualquer senha")
