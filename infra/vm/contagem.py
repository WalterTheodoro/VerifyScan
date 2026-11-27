"""Quantas linhas tem cada tabela, e a versão do alembic (ADR-0029).

É a conferência da migração (origem contra destino) e a da restauração (o que voltou da cópia).
As duas usam a mesma consulta, para os números serem comparáveis.
"""

# Uma linha por tabela, `nome|linhas`, e a versão do alembic. O `\gexec` do psql executa cada
# SELECT que a consulta de cima monta: é o jeito de contar todas as tabelas sem listá-las aqui.
CONSULTA = """\
SELECT 'alembic', version_num FROM alembic_version;
SELECT format('SELECT %L, count(*) FROM public.%I', tablename, tablename)
  FROM pg_tables
 WHERE schemaname = 'public' AND tablename <> 'alembic_version'
 ORDER BY tablename \\gexec
"""
# Texto para um `sh -c`: quem usa acrescenta a que banco ligar.
PSQL = "psql --no-psqlrc --tuples-only --no-align --field-separator='|' --set ON_ERROR_STOP=1"


def ler(saida: bytes) -> dict[str, str]:
    """O que o psql devolveu, como `{tabela: linhas}`; a versão do alembic fica em `alembic`."""
    contagens = {}
    for linha in saida.decode().splitlines():
        nome, _, valor = linha.partition("|")
        if nome:
            contagens[nome] = valor
    return contagens
