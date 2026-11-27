"""O que roda DENTRO da VM de produção (ADR-0029): deploy, backup e migração dos dados.

Só biblioteca padrão do Python 3.12, que já vem no Ubuntu da VM: nada é instalado para isto
rodar. Quem traz estes arquivos para a VM é o `entrar.sh`, pelo run-command, sempre na versão
exata do commit que está sendo publicado.
"""
