"""Fixtures compartilhadas.

Regra da Seção 6 do CLAUDE.md: teste não faz chamada de rede, nunca. As dependências de
infraestrutura entram na aplicação por `Depends` e são substituídas aqui por implementações
falsas determinísticas.
"""

import uuid
from collections.abc import AsyncIterator, Callable

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import obter_repositorio_analises
from app.main import criar_app
from app.schemas.health import SaudeServico
from app.services.health import VerificadorSaude
from app.services.repositorio_analises import RegistroAnalise

SERVICO_OK = SaudeServico(status="ok", latencia_ms=1.0)
SERVICO_FORA = SaudeServico(
    status="erro",
    latencia_ms=2000.0,
    detalhe="TimeoutError: timeout de 2.0s excedido",
)
SERVICO_DESATIVADO = SaudeServico(status="desativado", latencia_ms=0.0)


def verificador_falso(resultado: SaudeServico) -> Callable[[], VerificadorSaude]:
    """Monta um override de dependência que sempre responde `resultado`."""

    async def verificar() -> SaudeServico:
        return resultado

    return lambda: verificar


class RepositorioAnalisesEmMemoria:
    """Falso determinístico de `RepositorioAnalises`: guarda o que recebeu, numa lista."""

    def __init__(self) -> None:
        self.registros: list[RegistroAnalise] = []

    async def registrar(self, registro: RegistroAnalise) -> uuid.UUID:
        self.registros.append(registro)
        return uuid.uuid4()


@pytest.fixture
def repositorio() -> RepositorioAnalisesEmMemoria:
    return RepositorioAnalisesEmMemoria()


@pytest.fixture
def app(repositorio: RepositorioAnalisesEmMemoria) -> FastAPI:
    """Uma instância nova por teste, para que os overrides não vazem entre casos.

    O repositório real precisaria do banco; por padrão toda app de teste usa o falso em memória.
    """
    app = criar_app()
    app.dependency_overrides[obter_repositorio_analises] = lambda: repositorio
    return app


@pytest.fixture
async def cliente(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Fala com a app em memória: sem subir servidor e sem abrir porta.

    O `ASGITransport` não executa o `lifespan`, então o engine do Postgres e o cliente Redis
    reais nunca chegam a ser criados. É isso que garante o teste sem rede.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://teste") as cliente:
        yield cliente
