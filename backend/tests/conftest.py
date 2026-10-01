"""Fixtures compartilhadas.

Regra da Seção 6 do CLAUDE.md: teste não faz chamada de rede, nunca. As dependências de
infraestrutura entram na aplicação por `Depends` e são substituídas aqui por implementações
falsas determinísticas.
"""

import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import (
    obter_repositorio_analises,
    obter_repositorio_historico,
    obter_repositorio_sessoes,
    obter_repositorio_usuarios,
)
from app.core.config import Settings, get_settings
from app.main import criar_app
from app.schemas.health import SaudeServico
from app.services.health import VerificadorSaude
from app.services.repositorio_analises import RegistroAnalise
from app.services.repositorio_historico import AnaliseDoHistorico
from app.services.repositorio_usuarios import (
    CredenciaisArmazenadas,
    DadosConta,
    EmailJaCadastrado,
    UsuarioAutenticado,
)

SERVICO_OK = SaudeServico(status="ok", latencia_ms=1.0)
SERVICO_FORA = SaudeServico(
    status="erro",
    latencia_ms=2000.0,
    detalhe="TimeoutError: timeout de 2.0s excedido",
)
SERVICO_DESATIVADO = SaudeServico(status="desativado", latencia_ms=0.0)


def verificador_falso(resultado: SaudeServico) -> Callable[[], VerificadorSaude]:
    """Monta um override de dependência que sempre responde `resultado`."""

    async def verificar() -> SaudeServico:
        return resultado

    return lambda: verificar


class RepositorioAnalisesEmMemoria:
    """Falso determinístico de `RepositorioAnalises`: guarda o que recebeu, numa lista."""

    def __init__(self) -> None:
        self.registros: list[RegistroAnalise] = []

    async def registrar(self, registro: RegistroAnalise) -> uuid.UUID:
        self.registros.append(registro)
        return uuid.uuid4()


class RelogioFalso:
    """Relógio controlado pelo teste. No Postgres quem dá a hora é o `now()` do banco."""

    def __init__(self) -> None:
        self.agora = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.agora


@dataclass
class SessaoEmMemoria:
    usuario_id: uuid.UUID
    token_hash: str
    expira_em: datetime


class RepositorioSessoesEmMemoria:
    """Falso determinístico de `RepositorioSessoes`. Lê os usuários do falso de usuários."""

    def __init__(self, relogio: RelogioFalso) -> None:
        self.relogio = relogio
        self.sessoes: list[SessaoEmMemoria] = []
        self.usuarios: dict[uuid.UUID, UsuarioAutenticado] = {}

    async def criar(self, usuario_id: uuid.UUID, token_hash: str, validade: timedelta) -> None:
        self.sessoes.append(SessaoEmMemoria(usuario_id, token_hash, self.relogio() + validade))

    async def buscar_usuario(self, token_hash: str) -> UsuarioAutenticado | None:
        for sessao in self.sessoes:
            if sessao.token_hash == token_hash and sessao.expira_em > self.relogio():
                return self.usuarios[sessao.usuario_id]
        return None

    async def apagar(self, token_hash: str) -> None:
        self.sessoes = [s for s in self.sessoes if s.token_hash != token_hash]

    async def apagar_vencidas(self, usuario_id: uuid.UUID) -> None:
        self.sessoes = [
            s
            for s in self.sessoes
            if not (s.usuario_id == usuario_id and s.expira_em <= self.relogio())
        ]


class RepositorioUsuariosEmMemoria:
    """Falso determinístico de `RepositorioUsuarios`. O e-mail é a chave, como o UNIQUE."""

    def __init__(self, sessoes: RepositorioSessoesEmMemoria) -> None:
        self.sessoes = sessoes
        self.credenciais: dict[str, CredenciaisArmazenadas] = {}
        self.criados_em: dict[uuid.UUID, datetime] = {}

    async def criar_com_sessao(
        self, nome: str, email: str, senha_hash: str, token_hash: str, validade: timedelta
    ) -> UsuarioAutenticado:
        if email in self.credenciais:
            raise EmailJaCadastrado()
        usuario = UsuarioAutenticado(id=uuid.uuid4(), nome=nome, email=email)
        self.credenciais[email] = CredenciaisArmazenadas(usuario, senha_hash)
        self.criados_em[usuario.id] = self.sessoes.relogio()
        self.sessoes.usuarios[usuario.id] = usuario
        await self.sessoes.criar(usuario.id, token_hash, validade)
        return usuario

    async def buscar_credenciais(self, email: str) -> CredenciaisArmazenadas | None:
        return self.credenciais.get(email)

    async def atualizar_senha_hash(self, usuario_id: uuid.UUID, senha_hash: str) -> None:
        for email, atual in self.credenciais.items():
            if atual.usuario.id == usuario_id:
                self.credenciais[email] = CredenciaisArmazenadas(atual.usuario, senha_hash)

    async def buscar_conta(self, usuario_id: uuid.UUID) -> DadosConta | None:
        for atual in self.credenciais.values():
            if atual.usuario.id == usuario_id:
                return DadosConta(
                    nome=atual.usuario.nome,
                    email=atual.usuario.email,
                    criado_em=self.criados_em[usuario_id],
                )
        return None


@dataclass
class AnaliseVinculada:
    """Uma linha de `analises` no falso: o dono pode virar `None` (desvinculação)."""

    dono: uuid.UUID | None
    analise: AnaliseDoHistorico


class RepositorioHistoricoEmMemoria:
    """Falso determinístico de `RepositorioHistorico`, com a janela medida pelo relógio falso.

    As regras de janela e de dono valem aqui como no SQL; quem prova o SQL de verdade são os
    testes de `tests/integracao/test_historico.py`.
    """

    def __init__(self, relogio: RelogioFalso) -> None:
        self.relogio = relogio
        self.linhas: list[AnaliseVinculada] = []
        self.desvinculacoes = 0

    def adicionar(self, dono: uuid.UUID | None, analise: AnaliseDoHistorico) -> None:
        self.linhas.append(AnaliseVinculada(dono, analise))

    async def listar(
        self, usuario_id: uuid.UUID, janela: timedelta, limite: int
    ) -> list[AnaliseDoHistorico]:
        limite_da_janela = self.relogio() - janela
        dentro = [
            linha.analise
            for linha in self.linhas
            if linha.dono == usuario_id and linha.analise.criada_em > limite_da_janela
        ]
        return sorted(dentro, key=lambda analise: analise.criada_em, reverse=True)[:limite]

    async def apagar(self, usuario_id: uuid.UUID, analise_id: uuid.UUID) -> bool:
        antes = len(self.linhas)
        self.linhas = [
            linha
            for linha in self.linhas
            if not (linha.dono == usuario_id and linha.analise.id == analise_id)
        ]
        return len(self.linhas) < antes

    async def apagar_todas(self, usuario_id: uuid.UUID) -> int:
        antes = len(self.linhas)
        self.linhas = [linha for linha in self.linhas if linha.dono != usuario_id]
        return antes - len(self.linhas)

    async def desvincular_vencidas(self, janela: timedelta) -> int:
        self.desvinculacoes += 1
        limite_da_janela = self.relogio() - janela
        vencidas = [
            linha
            for linha in self.linhas
            if linha.dono is not None and linha.analise.criada_em <= limite_da_janela
        ]
        for linha in vencidas:
            linha.dono = None
        return len(vencidas)


@pytest.fixture
def repositorio() -> RepositorioAnalisesEmMemoria:
    return RepositorioAnalisesEmMemoria()


@pytest.fixture
def relogio() -> RelogioFalso:
    return RelogioFalso()


@pytest.fixture
def sessoes(relogio: RelogioFalso) -> RepositorioSessoesEmMemoria:
    return RepositorioSessoesEmMemoria(relogio)


@pytest.fixture
def usuarios(sessoes: RepositorioSessoesEmMemoria) -> RepositorioUsuariosEmMemoria:
    return RepositorioUsuariosEmMemoria(sessoes)


@pytest.fixture
def historico(relogio: RelogioFalso) -> RepositorioHistoricoEmMemoria:
    return RepositorioHistoricoEmMemoria(relogio)


def settings_de_teste(**valores: object) -> Settings:
    """Settings sem o `.env`: o COOKIE_SECURE=false do `.env` local não decide o teste."""
    return Settings(_env_file=None, **valores)  # type: ignore[call-arg]


@pytest.fixture
def app(
    repositorio: RepositorioAnalisesEmMemoria,
    usuarios: RepositorioUsuariosEmMemoria,
    sessoes: RepositorioSessoesEmMemoria,
    historico: RepositorioHistoricoEmMemoria,
) -> FastAPI:
    """Uma instância nova por teste, para que os overrides não vazem entre casos.

    Os repositórios reais precisariam do banco; por padrão toda app de teste usa os falsos em
    memória, e a configuração é a default de produção (cookie Secure).
    """
    app = criar_app()
    app.dependency_overrides[obter_repositorio_analises] = lambda: repositorio
    app.dependency_overrides[obter_repositorio_usuarios] = lambda: usuarios
    app.dependency_overrides[obter_repositorio_sessoes] = lambda: sessoes
    app.dependency_overrides[obter_repositorio_historico] = lambda: historico
    # Lambda, e não a função direto: o FastAPI lê a assinatura do override, e o `**valores`
    # viraria parâmetro da requisição (422 em toda rota — aconteceu).
    app.dependency_overrides[get_settings] = lambda: settings_de_teste()
    return app


@pytest.fixture
async def cliente(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Fala com a app em memória: sem subir servidor e sem abrir porta.

    O `ASGITransport` não executa o `lifespan`, então o engine do Postgres e o cliente Redis
    reais nunca chegam a ser criados. É isso que garante o teste sem rede.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://teste") as cliente:
        yield cliente
