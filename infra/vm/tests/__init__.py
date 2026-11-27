"""Testes do que roda na VM. Nada aqui fala com a rede nem com o Docker: o Azure e os comandos
do sistema entram por parâmetro e são trocados por falsos (CLAUDE.md §6).

    cd backend
    uv run pytest ../infra -q
"""
