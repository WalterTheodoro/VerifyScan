"""Normalização de texto — a mesma função roda no conteúdo do usuário e nos padrões do YAML.

É isso que permite escrever `'últimas horas'` no `regras.yaml` e casar com `ÚLTIMAS  HORAS`
sem espalhar `re.IGNORECASE` e variantes acentuadas pelos padrões (ADR-0008).

Módulo sem nenhuma dependência do projeto, de propósito: quem o importa não herda nada.
"""

import re
import unicodedata

_ESPACOS = re.compile(r"\s+")


def normalizar(texto: str) -> str:
    """Minúsculas, sem acento, com os espaços colapsados em um só.

    Colapsar quebra de linha em espaço é intencional: mensagem de WhatsApp quebra linha no meio
    da frase, e sem isso `'banco do brasil informa'` não casaria com o texto quebrado em duas.
    """
    decomposto = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return _ESPACOS.sub(" ", sem_acento).strip().lower()
