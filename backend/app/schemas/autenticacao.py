"""Contrato de /api/auth.

Os campos têm default vazio de propósito: campo ausente chega ao service e é recusado com frase
em pt-BR, em vez do 422 padrão do FastAPI, que sai em inglês. O corpo em si continua
obrigatório e só é aceito como JSON — parte da defesa de CSRF do ADR-0013.
"""

from pydantic import BaseModel


class SolicitacaoCadastro(BaseModel):
    nome: str = ""
    email: str = ""
    senha: str = ""


class SolicitacaoLogin(BaseModel):
    email: str = ""
    senha: str = ""


class RespostaUsuario(BaseModel):
    """O que a interface precisa para saudar a pessoa. Sem id, sem token."""

    nome: str
    email: str
