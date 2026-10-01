"""ServicoAutenticacao com repositórios em memória — validação, sessão e o que não pode vazar.

Os casos contra o Postgres real (UNIQUE, CASCADE, relógio do banco) estão em
`tests/integracao/test_autenticacao.py`.
"""

import asyncio
import logging
from datetime import timedelta

import pytest
from argon2 import PasswordHasher

from app.core.seguranca import HasherSenha
from app.services.analise import EntradaInvalida
from app.services.autenticacao import (
    CredenciaisInvalidas,
    ServicoAutenticacao,
    ServicoIndisponivel,
    hash_do_token,
    normalizar_email,
)
from app.services.repositorio_usuarios import CredenciaisArmazenadas, EmailJaCadastrado
from tests.conftest import (
    RelogioFalso,
    RepositorioSessoesEmMemoria,
    RepositorioUsuariosEmMemoria,
)

NOME = "Maria"
EMAIL = "maria@exemplo.com"
SENHA = "uma senha boa"


class HasherEspiao(HasherSenha):
    """O hasher real, contando quantas vezes o hash de mentira foi verificado."""

    def __init__(self) -> None:
        super().__init__()
        self.verificacoes_falsas = 0

    async def verificar_contra_falso(self, senha: str) -> None:
        self.verificacoes_falsas += 1
        await super().verificar_contra_falso(senha)


@pytest.fixture(scope="module")
def hasher() -> HasherEspiao:
    return HasherEspiao()


@pytest.fixture
def servico(
    usuarios: RepositorioUsuariosEmMemoria,
    sessoes: RepositorioSessoesEmMemoria,
    hasher: HasherEspiao,
) -> ServicoAutenticacao:
    return ServicoAutenticacao(
        usuarios=usuarios, sessoes=sessoes, hasher=hasher, sessao_dias=7, timeout_s=5.0
    )


# ─── normalização e validação ─────────────────────────────────────────────────────────────


def test_email_e_normalizado_com_strip_e_minusculas() -> None:
    assert normalizar_email("  Maria@Exemplo.COM ") == "maria@exemplo.com"


async def test_cadastro_grava_o_email_normalizado(
    servico: ServicoAutenticacao, usuarios: RepositorioUsuariosEmMemoria
) -> None:
    aberta = await servico.cadastrar("  Maria  ", "  Maria@Exemplo.COM ", SENHA)

    assert aberta.usuario.email == "maria@exemplo.com"
    assert aberta.usuario.nome == "Maria"
    assert list(usuarios.credenciais) == ["maria@exemplo.com"]


@pytest.mark.parametrize(
    ("nome", "email", "senha", "mensagem"),
    [
        ("   ", EMAIL, SENHA, "Informe como você quer ser chamado."),
        ("x" * 61, EMAIL, SENHA, "O nome pode ter no máximo 60 caracteres."),
        (NOME, "maria.exemplo.com", SENHA, "Confira o e-mail"),
        (NOME, "maria@@exemplo.com", SENHA, "Confira o e-mail"),
        (NOME, "maria@exemplo", SENHA, "Confira o e-mail"),
        (NOME, "@exemplo.com", SENHA, "Confira o e-mail"),
        (NOME, "maria@.com", SENHA, "Confira o e-mail"),
        (NOME, "ma ria@exemplo.com", SENHA, "Confira o e-mail"),
        (NOME, "a" * 243 + "@exemplo.com", SENHA, "O e-mail pode ter no máximo 254 caracteres."),
        (NOME, EMAIL, "1234567", "A senha precisa ter pelo menos 8 caracteres."),
        (NOME, EMAIL, "x" * 129, "A senha pode ter no máximo 128 caracteres."),
    ],
)
async def test_cadastro_invalido_e_recusado_com_mensagem_em_portugues(
    servico: ServicoAutenticacao,
    usuarios: RepositorioUsuariosEmMemoria,
    nome: str,
    email: str,
    senha: str,
    mensagem: str,
) -> None:
    with pytest.raises(EntradaInvalida, match=mensagem):
        await servico.cadastrar(nome, email, senha)

    assert usuarios.credenciais == {}


@pytest.mark.parametrize(
    ("nome", "email", "senha"),
    [
        ("x" * 60, EMAIL, SENHA),
        ("  " + "x" * 60 + "  ", EMAIL, SENHA),
        (NOME, "a" * 242 + "@exemplo.com", SENHA),
        (NOME, EMAIL, "12345678"),
        (NOME, EMAIL, "x" * 128),
        (NOME, EMAIL, "senhasemnumero"),
    ],
)
async def test_cadastro_nos_limites_e_aceito(
    servico: ServicoAutenticacao, nome: str, email: str, senha: str
) -> None:
    """Sem regra de composição: o público tem baixo letramento digital (ADR-0013)."""
    aberta = await servico.cadastrar(nome, email, senha)

    assert aberta.token


async def test_senha_nao_sofre_strip(servico: ServicoAutenticacao) -> None:
    await servico.cadastrar(NOME, EMAIL, "  espaços contam  ")

    await servico.entrar(EMAIL, "  espaços contam  ")
    with pytest.raises(CredenciaisInvalidas):
        await servico.entrar(EMAIL, "espaços contam")


async def test_espacos_nas_pontas_contam_no_tamanho_da_senha(
    servico: ServicoAutenticacao,
) -> None:
    """Oito caracteres como digitada; com strip seriam seis, e o cadastro seria recusado."""
    aberta = await servico.cadastrar(NOME, EMAIL, " 123456 ")

    assert aberta.token


# ─── cadastro ─────────────────────────────────────────────────────────────────────────────


async def test_cadastro_ja_abre_sessao(servico: ServicoAutenticacao) -> None:
    aberta = await servico.cadastrar(NOME, EMAIL, SENHA)

    assert await servico.usuario_da_sessao(aberta.token) == aberta.usuario


async def test_email_duplicado_com_maiusculas_e_recusado(servico: ServicoAutenticacao) -> None:
    await servico.cadastrar(NOME, EMAIL, SENHA)

    with pytest.raises(EmailJaCadastrado, match=r"^Já existe uma conta com este e-mail\.$"):
        await servico.cadastrar("Outra", "MARIA@exemplo.com", "outra senha boa")


async def test_banco_guarda_o_hash_do_token_e_nao_o_token(
    servico: ServicoAutenticacao, sessoes: RepositorioSessoesEmMemoria
) -> None:
    aberta = await servico.cadastrar(NOME, EMAIL, SENHA)

    guardado = sessoes.sessoes[0].token_hash
    assert guardado != aberta.token
    assert guardado == hash_do_token(aberta.token)
    assert len(guardado) == 64


async def test_banco_guarda_argon2id_e_nao_a_senha(
    servico: ServicoAutenticacao, usuarios: RepositorioUsuariosEmMemoria
) -> None:
    await servico.cadastrar(NOME, EMAIL, SENHA)

    assert usuarios.credenciais[EMAIL].senha_hash.startswith("$argon2id$")


async def test_sessao_vale_sessao_dias(
    servico: ServicoAutenticacao, sessoes: RepositorioSessoesEmMemoria, relogio: RelogioFalso
) -> None:
    aberta = await servico.cadastrar(NOME, EMAIL, SENHA)

    assert sessoes.sessoes[0].expira_em == relogio.agora + timedelta(days=7)
    relogio.agora += timedelta(days=7)
    assert await servico.usuario_da_sessao(aberta.token) is None


# ─── login ────────────────────────────────────────────────────────────────────────────────


async def test_login_certo_abre_sessao_nova(servico: ServicoAutenticacao) -> None:
    cadastro = await servico.cadastrar(NOME, EMAIL, SENHA)

    login = await servico.entrar("  MARIA@exemplo.com", SENHA)

    assert login.usuario == cadastro.usuario
    assert login.token != cadastro.token
    assert await servico.usuario_da_sessao(login.token) == cadastro.usuario


async def test_email_inexistente_e_senha_errada_dao_a_mesma_resposta(
    servico: ServicoAutenticacao,
) -> None:
    await servico.cadastrar(NOME, EMAIL, SENHA)

    with pytest.raises(CredenciaisInvalidas) as senha_errada:
        await servico.entrar(EMAIL, "senha errada")
    with pytest.raises(CredenciaisInvalidas) as email_inexistente:
        await servico.entrar("ninguem@exemplo.com", SENHA)

    assert str(senha_errada.value) == str(email_inexistente.value) == "E-mail ou senha incorretos."


async def test_email_inexistente_verifica_o_hash_de_mentira(
    servico: ServicoAutenticacao, hasher: HasherEspiao
) -> None:
    """Sem a verificação, a resposta para conta inexistente sairia ~25 ms mais rápida."""
    antes = hasher.verificacoes_falsas

    with pytest.raises(CredenciaisInvalidas):
        await servico.entrar("ninguem@exemplo.com", SENHA)

    assert hasher.verificacoes_falsas == antes + 1


async def test_login_regrava_hash_com_parametros_antigos(
    servico: ServicoAutenticacao, usuarios: RepositorioUsuariosEmMemoria
) -> None:
    await servico.cadastrar(NOME, EMAIL, SENHA)
    usuario = usuarios.credenciais[EMAIL].usuario
    antigo = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash(SENHA)
    usuarios.credenciais[EMAIL] = CredenciaisArmazenadas(usuario, antigo)

    await servico.entrar(EMAIL, SENHA)

    assert usuarios.credenciais[EMAIL].senha_hash.startswith("$argon2id$v=19$m=19456,t=2,p=1$")


async def test_login_apaga_as_sessoes_vencidas_do_usuario(
    servico: ServicoAutenticacao, sessoes: RepositorioSessoesEmMemoria, relogio: RelogioFalso
) -> None:
    await servico.cadastrar(NOME, EMAIL, SENHA)
    relogio.agora += timedelta(days=8)

    login = await servico.entrar(EMAIL, SENHA)

    assert [s.token_hash for s in sessoes.sessoes] == [hash_do_token(login.token)]


# ─── sessão e logout ──────────────────────────────────────────────────────────────────────


async def test_token_desconhecido_ou_vazio_nao_autentica(servico: ServicoAutenticacao) -> None:
    assert await servico.usuario_da_sessao("token-que-nao-existe") is None
    assert await servico.usuario_da_sessao("") is None


async def test_sair_apaga_a_sessao(
    servico: ServicoAutenticacao, sessoes: RepositorioSessoesEmMemoria
) -> None:
    aberta = await servico.cadastrar(NOME, EMAIL, SENHA)

    await servico.sair(aberta.token)

    assert sessoes.sessoes == []
    assert await servico.usuario_da_sessao(aberta.token) is None


# ─── timeout do banco ─────────────────────────────────────────────────────────────────────


class RepositorioSessoesLento(RepositorioSessoesEmMemoria):
    async def buscar_usuario(self, token_hash: str) -> None:
        await asyncio.sleep(3600)
        raise AssertionError("o timeout deveria ter cortado antes")


async def test_banco_lento_vira_servico_indisponivel(
    usuarios: RepositorioUsuariosEmMemoria, hasher: HasherEspiao, relogio: RelogioFalso
) -> None:
    servico = ServicoAutenticacao(
        usuarios=usuarios,
        sessoes=RepositorioSessoesLento(relogio),
        hasher=hasher,
        sessao_dias=7,
        timeout_s=0.05,
    )

    with pytest.raises(
        ServicoIndisponivel,
        match=r"^O serviço está iniciando\. Tente de novo em alguns segundos\.$",
    ):
        await servico.usuario_da_sessao("qualquer")


class HasherLento(HasherSenha):
    async def gerar(self, senha: str) -> str:
        await asyncio.sleep(0.2)
        return await super().gerar(senha)


async def test_timeout_nao_conta_o_tempo_do_hash(
    usuarios: RepositorioUsuariosEmMemoria, sessoes: RepositorioSessoesEmMemoria
) -> None:
    """O timeout envolve só o I/O de banco: disputa de CPU não vira falso 503 (ADR-0013)."""
    servico = ServicoAutenticacao(
        usuarios=usuarios, sessoes=sessoes, hasher=HasherLento(), sessao_dias=7, timeout_s=0.1
    )

    aberta = await servico.cadastrar(NOME, EMAIL, SENHA)

    assert aberta.token


# ─── logs ─────────────────────────────────────────────────────────────────────────────────


async def test_logs_nao_identificam_conta_nem_segredo(
    servico: ServicoAutenticacao, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        aberta = await servico.cadastrar(NOME, EMAIL, SENHA)
        await servico.entrar(EMAIL, SENHA)
        with pytest.raises(CredenciaisInvalidas):
            await servico.entrar(EMAIL, "senha errada")
        with pytest.raises(CredenciaisInvalidas):
            await servico.entrar("ninguem@exemplo.com", "senha errada")
        await servico.sair(aberta.token)

    recusas = [r for r in caplog.records if r.name == "app.services.autenticacao"]
    assert len(recusas) == 2
    assert all(r.levelno == logging.INFO for r in recusas)
    proibidos = (EMAIL, "ninguem", SENHA, "senha errada", aberta.token, str(aberta.usuario.id))
    for proibido in (*proibidos, hash_do_token(aberta.token), "argon2"):
        assert proibido not in caplog.text
