"""GET /health — checa Postgres e Redis e reporta cada um separadamente."""

from fastapi import FastAPI
from httpx import AsyncClient

from app.api.deps import obter_verificador_postgres, obter_verificador_redis
from tests.conftest import SERVICO_FORA, SERVICO_OK, verificador_falso


async def test_health_com_tudo_no_ar(app: FastAPI, cliente: AsyncClient) -> None:
    app.dependency_overrides[obter_verificador_postgres] = verificador_falso(SERVICO_OK)
    app.dependency_overrides[obter_verificador_redis] = verificador_falso(SERVICO_OK)

    resposta = await cliente.get("/health")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] == "ok"
    assert corpo["postgres"]["status"] == "ok"
    assert corpo["redis"]["status"] == "ok"
    assert corpo["postgres"]["detalhe"] is None


async def test_health_com_redis_fora(app: FastAPI, cliente: AsyncClient) -> None:
    app.dependency_overrides[obter_verificador_postgres] = verificador_falso(SERVICO_OK)
    app.dependency_overrides[obter_verificador_redis] = verificador_falso(SERVICO_FORA)

    resposta = await cliente.get("/health")

    # 503 para que orquestrador e monitoramento enxerguem a degradação, mas o corpo mantém o
    # mesmo formato — é dele que a tela do frontend lê o status de cada serviço.
    assert resposta.status_code == 503
    corpo = resposta.json()
    assert corpo["status"] == "degradado"
    assert corpo["postgres"]["status"] == "ok"
    assert corpo["redis"]["status"] == "erro"
    assert "TimeoutError" in corpo["redis"]["detalhe"]


async def test_health_com_postgres_fora(app: FastAPI, cliente: AsyncClient) -> None:
    app.dependency_overrides[obter_verificador_postgres] = verificador_falso(SERVICO_FORA)
    app.dependency_overrides[obter_verificador_redis] = verificador_falso(SERVICO_OK)

    resposta = await cliente.get("/health")

    assert resposta.status_code == 503
    corpo = resposta.json()
    assert corpo["status"] == "degradado"
    assert corpo["postgres"]["status"] == "erro"
    assert corpo["postgres"]["detalhe"] is not None
    assert corpo["redis"]["status"] == "ok"


async def test_health_nao_abre_conexao_real(app: FastAPI, cliente: AsyncClient) -> None:
    """Guarda da regra 'teste não faz chamada de rede'.

    Engine e cliente Redis só nascem no `lifespan`, que o transporte em memória não executa.
    Se algum dia alguém criar a conexão dentro da rota, este teste quebra.
    """
    app.dependency_overrides[obter_verificador_postgres] = verificador_falso(SERVICO_OK)
    app.dependency_overrides[obter_verificador_redis] = verificador_falso(SERVICO_OK)

    await cliente.get("/health")

    assert not hasattr(app.state, "engine")
    assert not hasattr(app.state, "redis")
