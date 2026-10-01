"""Settings — a URL do banco aceita a string do Neon como ela vem, e o Redis é opcional."""

import pytest

from app.core.config import Settings, normalizar_database_url

QUERY_DO_NEON = "?sslmode=require&channel_binding=require"


@pytest.mark.parametrize(
    "entrada",
    [
        "postgresql://u:s@ep-exemplo.us-west-2.aws.neon.tech/neondb",
        "postgres://u:s@ep-exemplo.us-west-2.aws.neon.tech/neondb",
    ],
)
def test_esquema_sem_driver_vira_psycopg(entrada: str) -> None:
    """Sem o driver explícito, o SQLAlchemy procuraria o psycopg2, que não está instalado."""
    assert normalizar_database_url(entrada) == (
        "postgresql+psycopg://u:s@ep-exemplo.us-west-2.aws.neon.tech/neondb"
    )


def test_url_ja_normalizada_nao_muda() -> None:
    url = "postgresql+psycopg://verifyscan:senha@localhost:5432/verifyscan"

    assert normalizar_database_url(url) == url


def test_query_do_neon_e_preservada() -> None:
    url = "postgresql://u:s@ep-exemplo.neon.tech/neondb" + QUERY_DO_NEON

    assert normalizar_database_url(url) == (
        "postgresql+psycopg://u:s@ep-exemplo.neon.tech/neondb" + QUERY_DO_NEON
    )


def test_settings_aplica_a_normalizacao() -> None:
    settings = Settings(_env_file=None, database_url="postgres://u:s@h/db")  # type: ignore[call-arg]

    assert settings.database_url == "postgresql+psycopg://u:s@h/db"


@pytest.mark.parametrize("valor", [None, ""])
def test_redis_ausente_ou_vazio_significa_desativado(
    valor: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    if valor is not None:
        monkeypatch.setenv("REDIS_URL", valor)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.redis_url is None


def test_timeout_de_persistencia_tem_default() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.timeout_persistencia_s == 2.0


def test_autenticacao_tem_defaults_seguros() -> None:
    """Sem nada configurado, o cookie sai com Secure: esquecer a variável em produção não abre
    a sessão para HTTP. Quem desliga é o `.env` local."""
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.sessao_dias == 7
    assert settings.cookie_secure is True
    assert settings.timeout_autenticacao_s == 5.0
