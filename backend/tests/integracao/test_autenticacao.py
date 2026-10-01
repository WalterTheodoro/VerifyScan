"""Autenticação contra o Postgres real: UNIQUE, CASCADE, relógio do banco e tudo ou nada.

Dentro da transação externa do conftest, `now()` é o instante em que ela começou — fixo durante o
teste. Por isso a sessão vencida é fabricada com UPDATE, e não esperando o tempo passar.
"""

from datetime import timedelta

import pytest
from argon2 import PasswordHasher
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.seguranca import HasherSenha
from app.models import SessaoUsuario, Usuario
from app.services.autenticacao import ServicoAutenticacao, hash_do_token
from app.services.repositorio_sessoes import RepositorioSessoesPostgres
from app.services.repositorio_usuarios import EmailJaCadastrado, RepositorioUsuariosPostgres

pytestmark = pytest.mark.integracao

NOME = "Maria"
EMAIL = "maria@exemplo.com"
SENHA = "uma senha boa"


@pytest.fixture(scope="module")
def hasher() -> HasherSenha:
    return HasherSenha()


@pytest.fixture
def servico(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession], hasher: HasherSenha
) -> ServicoAutenticacao:
    return ServicoAutenticacao(
        usuarios=RepositorioUsuariosPostgres(fabrica_de_sessoes),
        sessoes=RepositorioSessoesPostgres(fabrica_de_sessoes),
        hasher=hasher,
        sessao_dias=7,
        timeout_s=5.0,
    )


async def _contar(sessao: AsyncSession, modelo: type[Usuario] | type[SessaoUsuario]) -> int:
    return await sessao.scalar(select(func.count()).select_from(modelo)) or 0


async def test_cadastro_grava_argon2id_e_hash_do_token(
    servico: ServicoAutenticacao, fabrica_de_sessoes: async_sessionmaker[AsyncSession]
) -> None:
    aberta = await servico.cadastrar(NOME, "  Maria@Exemplo.COM ", SENHA)

    async with fabrica_de_sessoes() as sessao:
        usuario = await sessao.get_one(Usuario, aberta.usuario.id)
        sessoes = (await sessao.scalars(select(SessaoUsuario))).all()

    assert usuario.email == EMAIL
    assert usuario.senha_hash.startswith("$argon2id$")
    assert SENHA not in usuario.senha_hash
    assert [s.token_hash for s in sessoes] == [hash_do_token(aberta.token)]
    assert sessoes[0].token_hash != aberta.token
    assert sessoes[0].expira_em - sessoes[0].created_at == timedelta(days=7)
    assert await servico.usuario_da_sessao(aberta.token) == aberta.usuario


async def test_email_duplicado_com_maiusculas_e_recusado_pelo_unique(
    servico: ServicoAutenticacao, fabrica_de_sessoes: async_sessionmaker[AsyncSession]
) -> None:
    await servico.cadastrar(NOME, EMAIL, SENHA)

    with pytest.raises(EmailJaCadastrado):
        await servico.cadastrar("Outra", "MARIA@Exemplo.com", "outra senha boa")

    async with fabrica_de_sessoes() as sessao:
        assert await _contar(sessao, Usuario) == 1
        assert await _contar(sessao, SessaoUsuario) == 1


async def test_cadastro_e_tudo_ou_nada(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    """Se a sessão não grava, a conta também não: o "tente de novo" não pode virar 409.

    O token_hash repetido faz o INSERT da sessão violar o UNIQUE de `sessoes` — uma violação que
    não é a do e-mail, então propaga como IntegrityError.
    """
    repositorio = RepositorioUsuariosPostgres(fabrica_de_sessoes)
    token_hash = hash_do_token("token")
    await repositorio.criar_com_sessao(NOME, EMAIL, "$argon2id$x", token_hash, timedelta(days=7))

    with pytest.raises(IntegrityError, match="uq_sessoes_token_hash"):
        await repositorio.criar_com_sessao(
            "Outra", "outra@exemplo.com", "$argon2id$y", token_hash, timedelta(days=7)
        )

    async with fabrica_de_sessoes() as sessao:
        emails = (await sessao.scalars(select(Usuario.email))).all()
    assert emails == [EMAIL]


async def test_sessao_vencida_nao_autentica_e_some_no_login_seguinte(
    servico: ServicoAutenticacao, fabrica_de_sessoes: async_sessionmaker[AsyncSession]
) -> None:
    vencida = await servico.cadastrar(NOME, EMAIL, SENHA)
    async with fabrica_de_sessoes() as sessao, sessao.begin():
        await sessao.execute(text("UPDATE sessoes SET expira_em = now() - interval '1 second'"))

    assert await servico.usuario_da_sessao(vencida.token) is None

    nova = await servico.entrar(EMAIL, SENHA)

    async with fabrica_de_sessoes() as sessao:
        hashes = (await sessao.scalars(select(SessaoUsuario.token_hash))).all()
    assert hashes == [hash_do_token(nova.token)]


async def test_login_regrava_hash_com_parametros_antigos(
    servico: ServicoAutenticacao, fabrica_de_sessoes: async_sessionmaker[AsyncSession]
) -> None:
    aberta = await servico.cadastrar(NOME, EMAIL, SENHA)
    antigo = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash(SENHA)
    async with fabrica_de_sessoes() as sessao, sessao.begin():
        await sessao.execute(text("UPDATE usuarios SET senha_hash = :h"), {"h": antigo})

    await servico.entrar(EMAIL, SENHA)

    async with fabrica_de_sessoes() as sessao:
        usuario = await sessao.get_one(Usuario, aberta.usuario.id)
    assert usuario.senha_hash.startswith("$argon2id$v=19$m=19456,t=2,p=1$")


async def test_sair_apaga_a_linha(
    servico: ServicoAutenticacao, fabrica_de_sessoes: async_sessionmaker[AsyncSession]
) -> None:
    aberta = await servico.cadastrar(NOME, EMAIL, SENHA)

    await servico.sair(aberta.token)

    async with fabrica_de_sessoes() as sessao:
        assert await _contar(sessao, SessaoUsuario) == 0
    assert await servico.usuario_da_sessao(aberta.token) is None


async def test_apagar_o_usuario_apaga_as_sessoes(
    servico: ServicoAutenticacao, fabrica_de_sessoes: async_sessionmaker[AsyncSession]
) -> None:
    """O motivo de não ser JWT: a sessão morre com a linha (ADR-0013)."""
    aberta = await servico.cadastrar(NOME, EMAIL, SENHA)
    await servico.entrar(EMAIL, SENHA)

    async with fabrica_de_sessoes() as sessao, sessao.begin():
        # SQL direto, sem passar pelo ORM: quem tem de apagar as sessões é o ON DELETE CASCADE.
        await sessao.execute(text("DELETE FROM usuarios WHERE id = :id"), {"id": aberta.usuario.id})

    async with fabrica_de_sessoes() as sessao:
        assert await _contar(sessao, SessaoUsuario) == 0
    assert await servico.usuario_da_sessao(aberta.token) is None


async def test_relacao_sem_selectinload_levanta_em_vez_de_fazer_io(
    servico: ServicoAutenticacao, fabrica_de_sessoes: async_sessionmaker[AsyncSession]
) -> None:
    aberta = await servico.cadastrar(NOME, EMAIL, SENHA)

    async with fabrica_de_sessoes() as sessao:
        usuario = await sessao.get_one(Usuario, aberta.usuario.id)
        with pytest.raises(Exception, match="lazy='raise'"):
            _ = usuario.sessoes
