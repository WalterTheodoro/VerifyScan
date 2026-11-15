"""O dia da cota vira à meia-noite de São Paulo, não à de UTC (ADR-0024)."""

from datetime import UTC, date, datetime

from app.core.relogio import dia_de_sao_paulo


def test_as_23h59_de_sao_paulo_ainda_e_o_mesmo_dia() -> None:
    # 02:59 UTC = 23:59 do dia anterior em São Paulo (UTC-3, sem horário de verão desde 2019).
    assert dia_de_sao_paulo(datetime(2026, 11, 15, 2, 59, tzinfo=UTC)) == date(2026, 11, 14)


def test_a_meia_noite_de_sao_paulo_vira_o_dia() -> None:
    assert dia_de_sao_paulo(datetime(2026, 11, 15, 3, 0, tzinfo=UTC)) == date(2026, 11, 15)


def test_a_meia_noite_de_utc_nao_vira_o_dia() -> None:
    assert dia_de_sao_paulo(datetime(2026, 11, 15, 0, 30, tzinfo=UTC)) == date(2026, 11, 14)
