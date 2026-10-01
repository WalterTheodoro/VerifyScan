"""Cadastro, login, sessão e logout (ADR-0013). A regra mora aqui; a rota só traduz para HTTP.

Duas regras atravessam o módulo:
- **O timeout envolve só o I/O de banco**, nunca o Argon2. O hash é CPU com custo fixo, numa
  thread; contá-lo no timeout transformaria disputa de CPU no plano gratuito em falso 503.
- **Log não identifica a conta.** Nada de e-mail, senha, token, hash nem id em mensagem de log.
"""

import asyncio
import hashlib
import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import NoReturn

from app.core.seguranca import HasherSenha
from app.services.analise import EntradaInvalida
from app.services.repositorio_sessoes import RepositorioSessoes
from app.services.repositorio_usuarios import RepositorioUsuarios, UsuarioAutenticado

logger = logging.getLogger(__name__)

NOME_MAXIMO = 60
EMAIL_MAXIMO = 254
SENHA_MINIMA = 8
SENHA_MAXIMA = 128


class CredenciaisInvalidas(Exception):
    """A mesma mensagem para e-mail inexistente e senha errada: não revela se a conta existe."""

    def __init__(self) -> None:
        super().__init__("E-mail ou senha incorretos.")


class ServicoIndisponivel(Exception):
    """O banco não respondeu dentro de `timeout_autenticacao_s` — tipicamente o Neon acordando."""

    def __init__(self) -> None:
        super().__init__("O serviço está iniciando. Tente de novo em alguns segundos.")


@dataclass(frozen=True)
class SessaoAberta:
    """Resultado de cadastro e login. O token só existe aqui e no cookie — no banco, o hash."""

    usuario: UsuarioAutenticado
    token: str


def normalizar_email(email: str) -> str:
    """Antes de gravar e antes de buscar: `Maria@X.com` e `maria@x.com` são a mesma conta."""
    return email.strip().lower()


def hash_do_token(token: str) -> str:
    """SHA-256 em hex. Sem sal nem custo: o token já tem 256 bits de aleatoriedade."""
    return hashlib.sha256(token.encode()).hexdigest()


class ServicoAutenticacao:
    def __init__(
        self,
        usuarios: RepositorioUsuarios,
        sessoes: RepositorioSessoes,
        hasher: HasherSenha,
        sessao_dias: int,
        timeout_s: float,
    ) -> None:
        self._usuarios = usuarios
        self._sessoes = sessoes
        self._hasher = hasher
        self._validade = timedelta(days=sessao_dias)
        self._timeout_s = timeout_s

    async def cadastrar(self, nome: str, email: str, senha: str) -> SessaoAberta:
        """A pessoa já sai logada: conta e sessão nascem juntas, numa transação."""
        nome = self._validar_nome(nome)
        email = self._validar_email(email)
        self._validar_senha(senha)
        senha_hash = await self._hasher.gerar(senha)
        token = secrets.token_urlsafe(32)
        async with self._banco():
            usuario = await self._usuarios.criar_com_sessao(
                nome, email, senha_hash, hash_do_token(token), self._validade
            )
        return SessaoAberta(usuario=usuario, token=token)

    async def entrar(self, email: str, senha: str) -> SessaoAberta:
        async with self._banco():
            credenciais = await self._usuarios.buscar_credenciais(normalizar_email(email))
        if credenciais is None:
            await self._hasher.verificar_contra_falso(senha)
            self._recusar()
        if not await self._hasher.verificar(credenciais.senha_hash, senha):
            self._recusar()

        usuario = credenciais.usuario
        # Gerado antes do bloco de banco: o Argon2 fica fora do timeout.
        novo_hash = (
            await self._hasher.gerar(senha)
            if self._hasher.precisa_rehash(credenciais.senha_hash)
            else None
        )
        token = secrets.token_urlsafe(32)
        async with self._banco():
            if novo_hash is not None:
                await self._usuarios.atualizar_senha_hash(usuario.id, novo_hash)
            await self._sessoes.apagar_vencidas(usuario.id)
            await self._sessoes.criar(usuario.id, hash_do_token(token), self._validade)
        return SessaoAberta(usuario=usuario, token=token)

    async def usuario_da_sessao(self, token: str) -> UsuarioAutenticado | None:
        if not token:
            return None
        async with self._banco():
            return await self._sessoes.buscar_usuario(hash_do_token(token))

    async def sair(self, token: str) -> None:
        if not token:
            return
        async with self._banco():
            await self._sessoes.apagar(hash_do_token(token))

    @asynccontextmanager
    async def _banco(self) -> AsyncIterator[None]:
        """Teto do I/O de banco (ADR-0002). Estourou: 503 ao usuário, nunca resposta pela metade."""
        try:
            async with asyncio.timeout(self._timeout_s):
                yield
        except TimeoutError as erro:
            logger.warning("Banco não respondeu em %.1f s na autenticação", self._timeout_s)
            raise ServicoIndisponivel() from erro

    @staticmethod
    def _recusar() -> NoReturn:
        # INFO e sem identificar a conta: o log não pode virar lista de e-mails cadastrados.
        logger.info("Login recusado")
        raise CredenciaisInvalidas()

    @staticmethod
    def _validar_nome(nome: str) -> str:
        nome = nome.strip()
        if not nome:
            raise EntradaInvalida("Informe como você quer ser chamado.")
        if len(nome) > NOME_MAXIMO:
            raise EntradaInvalida(f"O nome pode ter no máximo {NOME_MAXIMO} caracteres.")
        return nome

    @staticmethod
    def _validar_email(email: str) -> str:
        """Formato simples, sem dependência: um @, algo antes, domínio com ponto no meio.

        Não tenta ser a RFC 5322. O que importa é pegar o erro de digitação comum; e-mail que
        passa aqui e não existe só prejudica o próprio dono.
        """
        email = normalizar_email(email)
        if len(email) > EMAIL_MAXIMO:
            raise EntradaInvalida(f"O e-mail pode ter no máximo {EMAIL_MAXIMO} caracteres.")
        local, _, dominio = email.partition("@")
        valido = (
            email.count("@") == 1
            and bool(local)
            and "." in dominio
            and not dominio.startswith(".")
            and not dominio.endswith(".")
            and not any(caractere.isspace() for caractere in email)
        )
        if not valido:
            raise EntradaInvalida("Confira o e-mail: ele precisa ter o formato nome@exemplo.com.")
        return email

    @staticmethod
    def _validar_senha(senha: str) -> None:
        """Só tamanho, sem regra de composição e sem strip (ADR-0013).

        Regra de composição empurra quem tem baixo letramento digital para senha previsível
        ("Senha@123"). O teto existe para limitar o trabalho do hash, não por segurança.
        """
        if len(senha) < SENHA_MINIMA:
            raise EntradaInvalida(f"A senha precisa ter pelo menos {SENHA_MINIMA} caracteres.")
        if len(senha) > SENHA_MAXIMA:
            raise EntradaInvalida(f"A senha pode ter no máximo {SENHA_MAXIMA} caracteres.")
