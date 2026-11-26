# syntax=docker/dockerfile:1
#
# Imagem do backend (ADR-0029). Gerada no GitHub Actions e publicada no GHCR com o SHA do commit.
# A imagem é pública: nenhum segredo entra nela. Tudo o que o `Settings` lê chega em execução,
# pelo ambiente do contêiner.
#
#   docker build -t verifyscan-backend backend

# ── 1. dependências ──────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS dependencias

# O mesmo `uv` da máquina e do CI, em versão fixa: é ele que lê o uv.lock.
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv

WORKDIR /app

# UV_PYTHON_DOWNLOADS=never: usa o Python da imagem, o mesmo do estágio final, e não baixa outro.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Só os dois arquivos de dependência primeiro: mudar código não refaz esta camada.
# --locked falha se o uv.lock estiver desatualizado, como no CI. --no-dev deixa de fora pytest,
# ruff, mypy e o Playwright. --no-install-project: o código entra por cópia, no estágio final.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# ── 2. execução ──────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim

# Usuário sem privilégio e sem pasta própria: o processo não escreve em disco (invariante 2).
RUN useradd --system --uid 10001 --no-create-home verifyscan

WORKDIR /app

COPY --from=dependencias /app/.venv /app/.venv
# O Alembic vai junto: a migração roda com esta mesma imagem, antes de a aplicação subir.
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER verifyscan
EXPOSE 8000

# O mesmo comando documentado, com `--loop none` (ADR-0007: inofensivo no Linux, regra única).
# Forma de lista: o uvicorn é o processo 1 e recebe o SIGTERM do `docker stop` direto.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "none"]
