"""Contas no banco — mesmo padrão do `RepositorioAnalises`: um Protocol, uma implementação
Postgres e um falso em memória nos testes.
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

import psycopg
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql import func

from app.models import SessaoUsuario, Usuario

# Nome que a naming_convention da Base dá ao UNIQUE de usuarios.email (ADR-0012).
_UNIQUE_DO_EMAIL = "uq_usuarios_email"


class EmailJaCadastrado(Exception):
    """O e-mail já tem conta. Revelar isso é o custo aceito de não verificar e-mail (ADR-0013)."""

    def __init__(self) -> None:
        super().__init__("Já existe uma conta com este e-mail.")


@dataclass(frozen=True)
class UsuarioAutenticado:
    """O que sai do repositório sobre uma conta. Sem hash de senha e sem objeto do ORM."""

    id: uuid.UUID
    nome: str
    email: str


@dataclass(frozen=True)
class CredenciaisArmazenadas:
    """Só o login precisa do hash, e só ele recebe este tipo."""

    usuario: UsuarioAutenticado
    senha_hash: str


class RepositorioUsuarios(Protocol):
    async def criar_com_sessao(
        self, nome: str, email: str, senha_hash: str, token_hash: str, validade: timedelta
    ) -> UsuarioAutenticado: ...

    async def buscar_credenciais(self, email: str) -> CredenciaisArmazenadas | None: ...

    async def atualizar_senha_hash(self, usuario_id: uuid.UUID, senha_hash: str) -> None: ...


class RepositorioUsuariosPostgres:
    def __init__(self, fabrica_de_sessoes: async_sessionmaker[AsyncSession]) -> None:
        self._fabrica_de_sessoes = fabrica_de_sessoes

    async def criar_com_sessao(
        self, nome: str, email: str, senha_hash: str, token_hash: str, validade: timedelta
    ) -> UsuarioAutenticado:
        """Conta e primeira sessão numa transação só: ou as duas linhas, ou nenhuma.

        Em duas transações, um timeout na sessão deixaria a conta criada: o "tente de novo" do
        503 viraria 409 na nova tentativa de cadastro (ADR-0013).

        Não há SELECT antes: o UNIQUE do banco decide sempre, inclusive na corrida entre dois
        cadastros simultâneos. Só o UNIQUE do e-mail vira `EmailJaCadastrado`; qualquer outra
        violação propaga.
        """
        usuario = Usuario(
            nome_exibicao=nome,
            email=email,
            senha_hash=senha_hash,
            # Relógio do banco, como o created_at (ADR-0012).
            sessoes=[SessaoUsuario(token_hash=token_hash, expira_em=func.now() + validade)],
        )
        try:
            async with self._fabrica_de_sessoes() as sessao, sessao.begin():
                sessao.add(usuario)
        except IntegrityError as erro:
            if _constraint_violada(erro) == _UNIQUE_DO_EMAIL:
                raise EmailJaCadastrado() from erro
            raise
        return UsuarioAutenticado(id=usuario.id, nome=usuario.nome_exibicao, email=usuario.email)

    async def buscar_credenciais(self, email: str) -> CredenciaisArmazenadas | None:
        async with self._fabrica_de_sessoes() as sessao:
            usuario = await sessao.scalar(select(Usuario).where(Usuario.email == email))
        if usuario is None:
            return None
        return CredenciaisArmazenadas(
            usuario=UsuarioAutenticado(
                id=usuario.id, nome=usuario.nome_exibicao, email=usuario.email
            ),
            senha_hash=usuario.senha_hash,
        )

    async def atualizar_senha_hash(self, usuario_id: uuid.UUID, senha_hash: str) -> None:
        async with self._fabrica_de_sessoes() as sessao, sessao.begin():
            await sessao.execute(
                update(Usuario).where(Usuario.id == usuario_id).values(senha_hash=senha_hash)
            )


def _constraint_violada(erro: IntegrityError) -> str | None:
    if isinstance(erro.orig, psycopg.Error):
        return erro.orig.diag.constraint_name
    return None
