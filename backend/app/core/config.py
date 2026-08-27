"""Configuração da aplicação, lida do `.env` da raiz do repositório."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Variáveis de ambiente do backend.

    Só entram aqui as variáveis que a fase atual realmente usa. As demais estão
    documentadas em `.env.example` e passam a ser lidas na fase em que forem necessárias.
    """

    # O `.env` fica na raiz do monorepo, mas o backend costuma ser executado de dentro de
    # `backend/`. A tupla cobre os dois casos sem depender do diretório atual.
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "local"
    log_level: str = "INFO"

    # Origens autorizadas no CORS, separadas por vírgula.
    cors_origins: str = "http://localhost:3000"

    database_url: str = "postgresql+psycopg://verifyscan:verifyscan@localhost:5432/verifyscan"
    redis_url: str = "redis://localhost:6379/0"

    # Timeout das checagens de /health. Todo I/O externo tem timeout explícito (ADR-0002).
    timeout_health_s: float = 2.0

    @property
    def origens_cors(self) -> list[str]:
        return [origem.strip() for origem in self.cors_origins.split(",") if origem.strip()]


@lru_cache
def get_settings() -> Settings:
    """Instância única — evita reler o `.env` a cada requisição."""
    return Settings()
