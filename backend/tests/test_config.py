"""Settings — a URL do banco aceita a string do Neon como ela vem, e o Redis é opcional."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

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


def test_texto_max_caracteres_nao_passa_do_check_do_banco() -> None:
    """O CHECK `ck_analises_texto_ate_5000` da migração 0004 guarda até 5000 caracteres. Um limite
    maior aceitaria a análise e perderia o registro de quem está logado em silêncio (ADR-0018):
    o processo prefere não subir."""
    assert Settings(_env_file=None).texto_max_caracteres == 5000  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Settings(_env_file=None, texto_max_caracteres=5001)  # type: ignore[call-arg]


# ─── análise com IA (ADR-0020) ────────────────────────────────────────────────────────────

CHAVE_DE_TESTE = "sk-ant-teste-NAO-E-CHAVE-REAL-123"


def test_ia_vem_desligada_por_padrao() -> None:
    """Sem configurar nada, nenhuma chamada sai para a Anthropic: é o estado do CI."""
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.ia_ativada is False
    assert settings.anthropic_api_key is None
    assert settings.ia_modelo == "claude-haiku-5-5"
    assert settings.ia_timeout_s == 15
    assert settings.ia_max_tokens == 700


@pytest.mark.parametrize("chave", [None, "", "   "])
def test_ia_ligada_sem_chave_nao_sobe(chave: str | None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ligar a IA e esquecer a chave faria toda análise cair no plano B em silêncio. O processo
    prefere não subir, com a variável que falta escrita no erro."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    valores: dict[str, object] = {"ia_ativada": True}
    if chave is not None:
        valores["anthropic_api_key"] = chave

    with pytest.raises(ValidationError, match="ANTHROPIC_API_KEY"):
        Settings(_env_file=None, **valores)  # type: ignore[call-arg]


def test_erro_de_boot_da_ia_nao_ecoa_outras_variaveis() -> None:
    """O erro vai para o log do Render. Ele não pode carregar a senha do banco."""
    with pytest.raises(ValidationError) as erro:
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            ia_ativada=True,
            database_url="postgresql://u:SENHA_DO_BANCO@h/db",
        )

    assert "SENHA_DO_BANCO" not in str(erro.value)


def test_ia_ligada_com_chave_sobe_e_a_chave_nao_aparece() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, ia_ativada=True, anthropic_api_key=CHAVE_DE_TESTE
    )

    assert settings.anthropic_api_key is not None
    assert settings.anthropic_api_key.get_secret_value() == CHAVE_DE_TESTE
    assert CHAVE_DE_TESTE not in repr(settings)
    assert CHAVE_DE_TESTE not in str(settings)


def test_timeout_da_ia_nao_passa_do_orcamento() -> None:
    """A invariante 8 conta com 15 s para a IA. Subir exige rever a conta, não só a variável."""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ia_timeout_s=16)  # type: ignore[call-arg]


def test_o_processo_de_teste_roda_com_a_ia_desligada() -> None:
    """O `.env` local pode ligar a IA; o `conftest.py` desliga antes de qualquer leitura, para
    que nenhum teste chame a rede (CLAUDE.md §6)."""
    from app.core.config import get_settings

    assert get_settings().ia_ativada is False


# ─── fatia 10: cota, teto de gasto, segredos e login (ADR-0024) ──────────────────────────────


def test_defaults_da_cota_e_do_login() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert (settings.ia_cota_sem_conta, settings.ia_cota_com_conta) == (5, 25)
    assert settings.ia_teto_gasto_diario_usd == Decimal("1.00")
    assert settings.timeout_cota_s == 1.5
    assert (settings.login_falhas_por_conta, settings.login_falhas_por_ip) == (10, 30)
    assert settings.login_janela_minutos == 15
    assert settings.cadastros_por_ip_por_dia == 5
    assert settings.argon2_simultaneos == 2


@pytest.mark.parametrize(
    ("campo", "maximo"),
    [
        ("ia_cota_sem_conta", 200),
        ("ia_cota_com_conta", 500),
        ("ia_teto_gasto_diario_usd", 20),
        ("timeout_cota_s", 5),
    ],
)
def test_cota_e_teto_podem_subir_ate_a_trava_contra_engano(campo: str, maximo: float) -> None:
    """Num evento, a sala inteira sai por um IP só: a cota precisa poder subir sem mexer no
    código. O `le=` barra só o valor absurdo digitado por engano."""
    assert Settings(_env_file=None, **{campo: maximo})  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{campo: maximo + 1})  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "campo",
    [
        "login_falhas_por_conta",
        "login_falhas_por_ip",
        "login_janela_minutos",
        "cadastros_por_ip_por_dia",
        "argon2_simultaneos",
    ],
)
def test_limites_de_seguranca_so_baixam(campo: str) -> None:
    padrao = getattr(Settings(_env_file=None), campo)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{campo: padrao + 1})  # type: ignore[call-arg]


@pytest.mark.parametrize("segredo", ["IP_HMAC_SEGREDO", "PROXY_SEGREDO"])
def test_segredo_ausente_nao_sobe(segredo: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sem default: com um conhecido, o HMAC do IP se desfaria; sem o do proxy, todo visitante
    cairia numa cota só."""
    monkeypatch.delenv(segredo)

    with pytest.raises(ValidationError, match=segredo.lower()):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_segredo_curto_nao_sobe_e_nao_aparece_no_erro() -> None:
    curto = "curto-demais-0123"

    with pytest.raises(ValidationError) as erro:
        Settings(_env_file=None, ip_hmac_segredo=curto)  # type: ignore[call-arg]

    assert curto not in str(erro.value)


def test_segredos_nao_aparecem_no_repr() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.ip_hmac_segredo.get_secret_value() not in repr(settings)
    assert settings.proxy_segredo.get_secret_value() not in repr(settings)
