"""Configuração da aplicação, lida do `.env` da raiz do repositório."""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Esquemas que o Neon (e a maioria dos provedores) entrega sem o driver. O SQLAlchemy lê
# `postgresql://` como psycopg2, que não está instalado; o driver do projeto é o psycopg3
# (ADR-0001). `postgres://` é o apelido aceito pelo libpq, mas o SQLAlchemy não o reconhece.
_ESQUEMAS_SEM_DRIVER = ("postgresql://", "postgres://")
_ESQUEMA_DO_PROJETO = "postgresql+psycopg://"


def normalizar_database_url(url: str) -> str:
    """Troca só o esquema; usuário, host, banco e query (`sslmode`, ...) passam intactos."""
    for esquema in _ESQUEMAS_SEM_DRIVER:
        if url.startswith(esquema):
            return _ESQUEMA_DO_PROJETO + url.removeprefix(esquema)
    return url


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
    # Ausente ou vazia: Redis desativado — o estado de produção até a Fase 4. O /health
    # reporta "desativado" sem tocar a rede.
    redis_url: str | None = None

    # Teto da mensagem analisada. Acima disso a análise é recusada, nunca truncada — ver
    # `ServicoAnalise._validar`. É configuração para a Fase 2 poder ajustar se o corpus
    # mostrar recusa frequente.
    texto_max_caracteres: int = 5000

    # Timeout das checagens de /health. Todo I/O externo tem timeout explícito (ADR-0002).
    timeout_health_s: float = 2.0

    # Teto do registro da análise no banco. Estourar não derruba a análise (ADR-0012).
    timeout_persistencia_s: float = 2.0

    # Teto do I/O de banco da autenticação — consultas e commit, nunca o hash do Argon2.
    # Separado do de cima porque os dois falham de jeitos opostos: estourar a persistência
    # descarta o registro em silêncio; estourar este devolve 503 ao usuário (ADR-0013).
    timeout_autenticacao_s: float = 5.0

    # Validade absoluta da sessão, em dias. É também o Max-Age do cookie.
    sessao_dias: int = Field(default=7, gt=0)

    # Por quantos dias a análise feita logado fica ligada à conta (ADR-0015). Depois disso ela é
    # desvinculada e vira idêntica a uma anônima. A listagem nunca mostra nada fora da janela.
    historico_dias: int = Field(default=7, gt=0)

    # Atributo Secure do cookie de sessão. O default é o de produção: esquecer a variável no
    # Render não manda a sessão por HTTP. Só o `.env` local desliga (HTTP em localhost).
    cookie_secure: bool = True

    @field_validator("database_url")
    @classmethod
    def _normalizar_database_url(cls, valor: str) -> str:
        return normalizar_database_url(valor)

    @field_validator("redis_url")
    @classmethod
    def _redis_vazio_e_desativado(cls, valor: str | None) -> str | None:
        return valor or None

    @property
    def origens_cors(self) -> list[str]:
        return [origem.strip() for origem in self.cors_origins.split(",") if origem.strip()]


@lru_cache
def get_settings() -> Settings:
    """Instância única — evita reler o `.env` a cada requisição."""
    return Settings()
