"""Testes do backend.

Este arquivo roda antes de qualquer `conftest.py` e de qualquer import da aplicação. O `.env`
local pode ligar a IA (ADR-0020), e a variável de ambiente vence o arquivo: assim nenhum
`get_settings()` do processo de teste chama a Anthropic (CLAUDE.md §6).

Os dois segredos da fatia 10 (ADR-0024) não têm default: sem eles, nem `criar_app()` sobe. Os
valores daqui são só de teste e só entram se o ambiente não trouxer outros: `setdefault`, e não
atribuição, para o que o CI define continuar valendo. Como a variável vence o arquivo, os do
`.env` local nunca chegam aos testes.
"""

import os

os.environ["IA_ATIVADA"] = "false"
os.environ.setdefault("IP_HMAC_SEGREDO", "segredo-de-teste-do-hmac-do-ip-0123456789")
os.environ.setdefault("PROXY_SEGREDO", "segredo-de-teste-do-proxy-do-next-0123456789")
