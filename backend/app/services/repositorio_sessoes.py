"""Sessões opacas no banco (ADR-0013). Guarda só o SHA-256 do token, nunca o token.

A hora é sempre a do banco (`now()`), como o `created_at` do ADR-0012: validade e limpeza não
dependem do relógio do processo.
"""

import uuid
from datetime import timedelta
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql import func

from app.models import SessaoUsuario, Usuario
from app.services.repositorio_usuarios import UsuarioAutenticado


class RepositorioSessoes(Protocol):
    async def criar(self, usuario_id: uuid.UUID, token_hash: str, validade: timedelta) -> None: ...

    async def buscar_usuario(self, token_hash: str) -> UsuarioAutenticado | None: ...

    async def apagar(self, token_hash: str) -> None: ...

    async def apagar_vencidas(self, usuario_id: uuid.UUID) -> None: ...


class RepositorioSessoesPostgres:
    def __init__(self, fabrica_de_sessoes: async_sessionmaker[AsyncSession]) -> None:
        self._fabrica_de_sessoes = fabrica_de_sessoes

    async def criar(self, usuario_id: uuid.UUID, token_hash: str, validade: timedelta) -> None:
        async with self._fabrica_de_sessoes() as sessao, sessao.begin():
            sessao.add(
                SessaoUsuario(
                    usuario_id=usuario_id,
                    token_hash=token_hash,
                    expira_em=func.now() + validade,
                )
            )

    async def buscar_usuario(self, token_hash: str) -> UsuarioAutenticado | None:
        """Sessão vencida não autentica, mesmo que a linha ainda exista."""
        async with self._fabrica_de_sessoes() as sessao:
            linha = (
                await sessao.execute(
                    select(Usuario.id, Usuario.nome_exibicao, Usuario.email)
                    .join(SessaoUsuario, SessaoUsuario.usuario_id == Usuario.id)
                    .where(
                        SessaoUsuario.token_hash == token_hash,
                        SessaoUsuario.expira_em > func.now(),
                    )
                )
            ).one_or_none()
        if linha is None:
            return None
        return UsuarioAutenticado(id=linha.id, nome=linha.nome_exibicao, email=linha.email)

    async def apagar(self, token_hash: str) -> None:
        async with self._fabrica_de_sessoes() as sessao, sessao.begin():
            await sessao.execute(
                delete(SessaoUsuario).where(SessaoUsuario.token_hash == token_hash)
            )

    async def apagar_vencidas(self, usuario_id: uuid.UUID) -> None:
        async with self._fabrica_de_sessoes() as sessao, sessao.begin():
            await sessao.execute(
                delete(SessaoUsuario).where(
                    SessaoUsuario.usuario_id == usuario_id,
                    SessaoUsuario.expira_em <= func.now(),
                )
            )
