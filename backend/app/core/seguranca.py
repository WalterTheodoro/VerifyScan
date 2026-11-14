"""Hash de senha com Argon2id (ADR-0013).

Os parâmetros são o mínimo da OWASP, explícitos. Os defaults do argon2-cffi (64 MiB, p=4) não
cabem no Render gratuito (512 MB, 0,1 CPU): medido em 1 vCPU, 142,5 ms por hash contra 23,6 ms.

Hash e verificação são CPU puro. Rodam numa thread (`asyncio.to_thread`): no event loop, cada
login congelaria todas as requisições do processo durante o cálculo.

Cada cálculo ocupa ~19 MiB, e o Render gratuito tem 512 MB: umas 25 verificações simultâneas
derrubariam o processo. Por isso um semáforo deixa no máximo `vagas` calcularem ao mesmo tempo, e as
outras esperam (fatia 10, ADR-0024). Só a ESPERA tem teto; o cálculo em si continua fora de
qualquer timeout, como sempre foi (ADR-0013).
"""

import asyncio
import secrets
from collections.abc import Callable

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

ARGON2_TIME_COST = 2
ARGON2_MEMORY_COST_KIB = 19456  # 19 MiB
ARGON2_PARALLELISM = 1


class HasherOcupado(Exception):
    """Nenhuma vaga para o Argon2 dentro do teto de espera: muita gente entrando ao mesmo tempo."""


class HasherSenha:
    def __init__(self, vagas: int = 2, espera_s: float = 5.0) -> None:
        """`vagas`: cálculos ao mesmo tempo no processo. `espera_s`: quanto um pedido espera por
        uma vaga antes de desistir com `HasherOcupado` — o mesmo teto da autenticação.

        O semáforo se prende ao event loop em que esperou pela primeira vez. Em produção há um só;
        nos testes, cada um tem o seu, e quem testa a espera usa uma instância nova.
        """
        self._hasher = PasswordHasher(
            time_cost=ARGON2_TIME_COST,
            memory_cost=ARGON2_MEMORY_COST_KIB,
            parallelism=ARGON2_PARALLELISM,
        )
        # Hash de uma senha que ninguém conhece, gerado uma vez por processo. Login com e-mail
        # inexistente verifica contra ele, para gastar o mesmo tempo de uma conta que existe:
        # sem isso, a resposta mais rápida revelaria quais e-mails têm conta.
        self._hash_falso = self._hasher.hash(secrets.token_urlsafe(32))
        self._vagas = asyncio.Semaphore(vagas)
        self._espera_s = espera_s

    async def gerar(self, senha: str) -> str:
        return await self._numa_vaga(self._hasher.hash, senha)

    async def verificar(self, senha_hash: str, senha: str) -> bool:
        return await self._numa_vaga(self._verificar, senha_hash, senha)

    async def verificar_contra_falso(self, senha: str) -> None:
        await self.verificar(self._hash_falso, senha)

    def precisa_rehash(self, senha_hash: str) -> bool:
        """Verdadeiro se o hash foi gerado com outros parâmetros. Só lê o cabeçalho: barato."""
        return self._hasher.check_needs_rehash(senha_hash)

    async def _numa_vaga[T](self, calculo: Callable[..., T], *argumentos: str) -> T:
        try:
            async with asyncio.timeout(self._espera_s):
                await self._vagas.acquire()
        except TimeoutError as erro:
            raise HasherOcupado() from erro
        try:
            return await asyncio.to_thread(calculo, *argumentos)
        finally:
            self._vagas.release()

    def _verificar(self, senha_hash: str, senha: str) -> bool:
        # Senha errada (VerifyMismatchError é subclasse de VerificationError) e hash corrompido
        # têm o mesmo destino: recusar, nunca virar 500. O argon2-cffi codifica o hash em ASCII,
        # então hash corrompido com acento sai como UnicodeEncodeError (pego por teste).
        try:
            return self._hasher.verify(senha_hash, senha)
        except (VerificationError, InvalidHashError, UnicodeEncodeError):
            return False
