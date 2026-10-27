"""Contas no banco — mesmo padrão do `RepositorioAnalises`: um Protocol, uma implementação
Postgres e um falso em memória nos testes.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

import psycopg
from sqlalchemy import delete, select, update
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


@dataclass(frozen=True)
class DadosConta:
    """O que a seção "Meus dados" mostra. Sem id e sem hash de senha."""

    nome: str
    email: str
    criado_em: datetime


class RepositorioUsuarios(Protocol):
    async def criar_com_sessao(
        self, nome: str, email: str, senha_hash: str, token_hash: str, validade: timedelta
    ) -> UsuarioAutenticado: ...

    async def buscar_credenciais(self, email: str) -> CredenciaisArmazenadas | None: ...

    async def atualizar_senha_hash(self, usuario_id: uuid.UUID, senha_hash: str) -> None: ...

    async def buscar_conta(self, usuario_id: uuid.UUID) -> DadosConta | None: ...

    async def trocar_senha(
        self, usuario_id: uuid.UUID, senha_hash: str, token_hash_mantido: str
    ) -> None: ...

    async def apagar(self, usuario_id: uuid.UUID) -> None: ...


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

    async def buscar_conta(self, usuario_id: uuid.UUID) -> DadosConta | None:
        async with self._fabrica_de_sessoes() as sessao:
            linha = (
                await sessao.execute(
                    select(Usuario.nome_exibicao, Usuario.email, Usuario.created_at).where(
                        Usuario.id == usuario_id
                    )
                )
            ).one_or_none()
        if linha is None:
            return None
        return DadosConta(nome=linha.nome_exibicao, email=linha.email, criado_em=linha.created_at)

    async def trocar_senha(
        self, usuario_id: uuid.UUID, senha_hash: str, token_hash_mantido: str
    ) -> None:
        """Hash novo e as outras sessões da conta apagadas, numa transação só (ADR-0019).

        Em duas transações, um timeout entre elas deixaria a senha trocada e o aparelho perdido
        ainda logado — justamente o caso de quem troca a senha por desconfiança.
        """
        async with self._fabrica_de_sessoes() as sessao, sessao.begin():
            await sessao.execute(
                update(Usuario).where(Usuario.id == usuario_id).values(senha_hash=senha_hash)
            )
            await sessao.execute(
                delete(SessaoUsuario).where(
                    SessaoUsuario.usuario_id == usuario_id,
                    SessaoUsuario.token_hash != token_hash_mantido,
                )
            )

    async def apagar(self, usuario_id: uuid.UUID) -> None:
        """Apaga a conta. Sessões, análises ligadas (com o texto) e os indicadores delas vão
        pelos ON DELETE CASCADE das migrações 0001, 0002 e 0003 — quem apaga é o banco."""
        async with self._fabrica_de_sessoes() as sessao, sessao.begin():
            await sessao.execute(delete(Usuario).where(Usuario.id == usuario_id))


def _constraint_violada(erro: IntegrityError) -> str | None:
    if isinstance(erro.orig, psycopg.Error):
        return erro.orig.diag.constraint_name
    return None
