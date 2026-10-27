"""Testes do backend.

Este arquivo roda antes de qualquer `conftest.py` e de qualquer import da aplicação. O `.env`
local pode ligar a IA (ADR-0020), e a variável de ambiente vence o arquivo: assim nenhum
`get_settings()` do processo de teste chama a Anthropic (CLAUDE.md §6).
"""

import os

os.environ["IA_ATIVADA"] = "false"
