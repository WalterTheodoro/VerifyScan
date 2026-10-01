"""Respostas de erro declaradas no OpenAPI, compartilhadas pelas rotas de conta.

Sem a declaração, o Swagger mostra o código como "Undocumented". Em todos, `detail` é a frase em
pt-BR para o usuário — é o que o frontend exibe.
"""

from typing import Any

from fastapi import status

Respostas = dict[int | str, dict[str, Any]]

ERRO_401: Respostas = {
    status.HTTP_401_UNAUTHORIZED: {"description": "Sem sessão válida. `detail` diz o que fazer."}
}
ERRO_401_LOGIN: Respostas = {
    status.HTTP_401_UNAUTHORIZED: {
        "description": "E-mail ou senha incorretos, com o mesmo `detail` para os dois casos."
    }
}
ERRO_404_ANALISE: Respostas = {
    status.HTTP_404_NOT_FOUND: {
        "description": "Análise inexistente, com id inválido ou de outra conta — o mesmo "
        "`detail` nos três casos, para não revelar que ela existe."
    }
}
ERRO_409: Respostas = {
    status.HTTP_409_CONFLICT: {"description": "Já existe conta com este e-mail. `detail` diz isso."}
}
ERRO_422: Respostas = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "description": "Dado recusado. `detail` é a frase em pt-BR. Corpo que não é JSON válido "
        "mantém o formato padrão do FastAPI (`detail` em lista)."
    }
}
ERRO_503: Respostas = {
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "description": "Banco fora ou lento demais. `detail` pede para tentar de novo."
    }
}
