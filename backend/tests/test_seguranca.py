"""Hasher de senha: Argon2id com os parâmetros mínimos da OWASP (ADR-0013)."""

import asyncio
import threading
import time

import pytest
from argon2 import PasswordHasher

from app.core.seguranca import HasherOcupado, HasherSenha


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


# ─── semáforo (fatia 10, ADR-0024) ───────────────────────────────────────────────────────────


class HasherMedido(HasherSenha):
    """Troca o cálculo por uma espera, e mede quantos rodam ao mesmo tempo.

    Instância nova em cada teste: o `asyncio.Semaphore` se prende ao event loop em que esperou
    pela primeira vez, e cada teste do pytest-asyncio tem o seu.
    """

    def __init__(self, vagas: int, espera_s: float, duracao_s: float) -> None:
        super().__init__(vagas=vagas, espera_s=espera_s)
        self.duracao_s = duracao_s
        self.agora = 0
        self.maximo = 0
        self._trava = threading.Lock()

    def _verificar(self, senha_hash: str, senha: str) -> bool:
        with self._trava:
            self.agora += 1
            self.maximo = max(self.maximo, self.agora)
        time.sleep(self.duracao_s)
        with self._trava:
            self.agora -= 1
        return False


async def test_no_maximo_duas_verificacoes_ao_mesmo_tempo() -> None:
    """Cada Argon2id ocupa ~19 MiB; no Render, 512 MB. As outras esperam a vez."""
    hasher = HasherMedido(vagas=2, espera_s=5, duracao_s=0.05)

    resultados = await asyncio.gather(*(hasher.verificar("h", "s") for _ in range(8)))

    assert resultados == [False] * 8
    assert hasher.maximo == 2


async def test_espera_acima_do_teto_vira_hasher_ocupado() -> None:
    hasher = HasherMedido(vagas=1, espera_s=0.05, duracao_s=0.5)

    resultados = await asyncio.gather(
        hasher.verificar("h", "s"), hasher.verificar("h", "s"), return_exceptions=True
    )

    assert resultados.count(False) == 1
    assert sum(isinstance(r, HasherOcupado) for r in resultados) == 1


async def test_a_vaga_volta_mesmo_quando_o_calculo_falha() -> None:
    class HasherQueFalha(HasherSenha):
        def _verificar(self, senha_hash: str, senha: str) -> bool:
            raise RuntimeError("falhou")

    hasher = HasherQueFalha(vagas=1, espera_s=0.05)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            await hasher.verificar("h", "s")
