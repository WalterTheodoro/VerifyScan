"""No CI, a falta de TEST_DATABASE_URL reprova a coleta; local, só pula os testes de integração.

Sem esta regra, um CI que perdesse a variável ficaria verde com os testes de banco pulados —
o mesmo "verde sem testar" que deixou o bug do ADR-0007 passar.

Roda o pytest num subprocesso, só coletando `tests/integracao`: não abre conexão nenhuma.
`TEST_DATABASE_URL=""` vence o `.env` (variável de ambiente tem precedência no
pydantic-settings), então o teste não depende do `.env` de quem o executa.
"""

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _coletar_integracao(ci: bool) -> subprocess.CompletedProcess[str]:
    ambiente = {k: v for k, v in os.environ.items() if k != "CI"}
    ambiente["TEST_DATABASE_URL"] = ""
    ambiente["PYTHONIOENCODING"] = "utf-8"
    if ci:
        ambiente["CI"] = "true"
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/integracao",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        cwd=BACKEND,
        env=ambiente,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )


def test_no_ci_sem_test_database_url_a_coleta_falha() -> None:
    resultado = _coletar_integracao(ci=True)

    assert resultado.returncode != 0
    assert "TEST_DATABASE_URL" in resultado.stdout + resultado.stderr


def test_local_sem_test_database_url_a_coleta_passa() -> None:
    """Fora do CI a coleta segue; os testes caem no skip na hora de rodar."""
    resultado = _coletar_integracao(ci=False)

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
