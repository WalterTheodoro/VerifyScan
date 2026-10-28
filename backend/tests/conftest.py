"""Fixtures compartilhadas.

Regra da Seção 6 do CLAUDE.md: teste não faz chamada de rede, nunca. As dependências de
infraestrutura entram na aplicação por `Depends` e são substituídas aqui por implementações
falsas determinísticas.
"""

import asyncio
import base64
import dataclasses
import io
import json
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.api.deps import (
    obter_analisador_ia,
    obter_leitor_de_print,
    obter_repositorio_analises,
    obter_repositorio_historico,
    obter_repositorio_sessoes,
    obter_repositorio_usuarios,
)
from app.core.config import Settings, get_settings
from app.formulator.analisador import AnalisadorIA
from app.formulator.cliente import RespostaIA
from app.main import criar_app
from app.ocr.leitura import LeitorDePrint
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


def saida_da_ia(**mudancas: object) -> str:
    """Uma resposta válida da IA, em JSON, com os campos trocados por `mudancas`."""
    valores: dict[str, object] = {
        "tipo": "falsa cobrança de taxa dos Correios",
        "sinais": ["Pede pagamento por Pix para liberar uma entrega."],
        "nivel_sugerido": "ALTO",
        "o_que_fazer": ["Não pague a taxa.", "Apague a mensagem e bloqueie o contato."],
    }
    valores.update(mudancas)
    return json.dumps(valores, ensure_ascii=False)


class ClienteIAFalso:
    """Falso determinístico de `ClienteIA`: responde `texto`, demora ou levanta `erro`.

    Guarda o que recebeu, para o teste conferir o que foi enviado à IA.
    """

    def __init__(
        self,
        texto: str = "",
        *,
        erro: Exception | None = None,
        demora_s: float = 0.0,
        motivo_parada: str = "end_turn",
    ) -> None:
        self.texto = texto or saida_da_ia()
        self.erro = erro
        self.demora_s = demora_s
        self.motivo_parada = motivo_parada
        self.chamadas: list[tuple[str, str]] = []

    async def gerar(self, sistema: str, entrada: str) -> RespostaIA:
        self.chamadas.append((sistema, entrada))
        if self.demora_s:
            await asyncio.sleep(self.demora_s)
        if self.erro is not None:
            raise self.erro
        return RespostaIA(
            texto=self.texto,
            motivo_parada=self.motivo_parada,
            modelo="claude-haiku-5-5",
            tokens_entrada=1000,
            tokens_saida=200,
        )


def png_de_teste(tamanho: tuple[int, int] = (390, 844)) -> bytes:
    """Um PNG de verdade, pequeno: o que o Pillow precisa para a imagem passar na validação."""
    saida = io.BytesIO()
    Image.new("RGB", tamanho, (245, 245, 245)).save(saida, "PNG")
    return saida.getvalue()


def corpo_de_print(imagem: bytes | None = None, texto: str | None = None) -> dict[str, object]:
    """O JSON de `POST /api/analises/imagem`."""
    corpo: dict[str, object] = {
        "imagem_base64": base64.b64encode(imagem or png_de_teste()).decode("ascii")
    }
    if texto is not None:
        corpo["texto"] = texto
    return corpo


def saida_da_leitura(mensagens: list[tuple[str, str]] | None = None, **mudancas: object) -> str:
    """Uma resposta válida da leitura do print, em JSON. `mensagens`: pares (de, texto)."""
    valores: dict[str, object] = {
        "canal": "whatsapp",
        "remetente_salvo": "nao",
        "aviso_do_app": "nao",
        "primeira_mensagem": "sim",
        "mensagens": [
            {"de": de, "texto": texto}
            for de, texto in (
                [("contato", "Seu pacote está retido. Pague a taxa de R$ 9,90 pelo PIX.")]
                if mensagens is None
                else mensagens
            )
        ],
        "tem_link_visivel": "nao",
        "legivel": "sim",
    }
    valores.update(mudancas)
    return json.dumps(valores, ensure_ascii=False)


class ClienteLeituraFalso:
    """Falso determinístico de `ClienteLeitura`: responde `texto`, demora ou levanta `erro`.

    Guarda só o tamanho da imagem recebida, não os bytes: o teste confere que ela chegou."""

    def __init__(
        self,
        texto: str = "",
        *,
        erro: Exception | None = None,
        demora_s: float = 0.0,
        motivo_parada: str = "end_turn",
    ) -> None:
        self.texto = texto or saida_da_leitura()
        self.erro = erro
        self.demora_s = demora_s
        self.motivo_parada = motivo_parada
        self.chamadas: list[tuple[str, int]] = []

    async def ler(self, sistema: str, jpeg: bytes, schema: dict[str, object]) -> RespostaIA:
        self.chamadas.append((sistema, len(jpeg)))
        if self.demora_s:
            await asyncio.sleep(self.demora_s)
        if self.erro is not None:
            raise self.erro
        return RespostaIA(
            texto=self.texto,
            motivo_parada=self.motivo_parada,
            modelo="claude-haiku-5-5",
            tokens_entrada=4500,
            tokens_saida=300,
        )


def ia_desligada() -> AnalisadorIA:
    """Override de `obter_analisador_ia` com a IA desligada: o padrão de toda app de teste."""
    return AnalisadorIA(None, timeout_s=15)


def leitura_desligada() -> LeitorDePrint:
    """Override de `obter_leitor_de_print` com a IA desligada, par do `ia_desligada`."""
    return LeitorDePrint(None, timeout_s=10)


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

    async def apagar_todas_vencidas(self) -> int:
        antes = len(self.sessoes)
        self.sessoes = [s for s in self.sessoes if s.expira_em > self.relogio()]
        return antes - len(self.sessoes)


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

    async def trocar_senha(
        self, usuario_id: uuid.UUID, senha_hash: str, token_hash_mantido: str
    ) -> None:
        await self.atualizar_senha_hash(usuario_id, senha_hash)
        self.sessoes.sessoes = [
            s
            for s in self.sessoes.sessoes
            if s.usuario_id != usuario_id or s.token_hash == token_hash_mantido
        ]

    async def apagar(self, usuario_id: uuid.UUID) -> None:
        """O que o ON DELETE CASCADE faz no banco: a conta leva as sessões junto."""
        self.credenciais = {
            email: atual
            for email, atual in self.credenciais.items()
            if atual.usuario.id != usuario_id
        }
        self.sessoes.sessoes = [s for s in self.sessoes.sessoes if s.usuario_id != usuario_id]
        self.sessoes.usuarios.pop(usuario_id, None)

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
            # Como o UPDATE real: o dono, o texto, a explicação da IA e o contexto do print saem
            # juntos (ADR-0020, ADR-0023).
            linha.dono = None
            linha.analise = dataclasses.replace(
                linha.analise, texto=None, explicacao_ia=None, contexto_print=None
            )
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
    memória, e a configuração é a default de produção (cookie Secure). A IA começa desligada; o
    teste que a quer troca o `obter_analisador_ia` por um com o `ClienteIAFalso`.
    """
    app = criar_app()
    app.dependency_overrides[obter_repositorio_analises] = lambda: repositorio
    app.dependency_overrides[obter_repositorio_usuarios] = lambda: usuarios
    app.dependency_overrides[obter_repositorio_sessoes] = lambda: sessoes
    app.dependency_overrides[obter_repositorio_historico] = lambda: historico
    app.dependency_overrides[obter_analisador_ia] = ia_desligada
    app.dependency_overrides[obter_leitor_de_print] = leitura_desligada
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
