"""Registro da análise anônima contra o Postgres real (invariante 6, ADR-0012)."""

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.api.deps import obter_servico_analise
from app.models import Analise, IndicadorRisco
from app.schemas.analise import Fator
from app.services.orquestrador import OrquestradorAnalise
from app.services.repositorio_analises import RegistroAnalise, RepositorioAnalisesPostgres

pytestmark = pytest.mark.integracao

FATORES = (
    Fator(tipo="texto", categoria="urgencia", descricao="Pede pressa.", peso=10),
    Fator(tipo="texto", categoria="ameaca_bloqueio", descricao="Ameaça bloquear.", peso=15),
    Fator(tipo="texto", categoria="solicitacao_financeira", descricao="Pede PIX.", peso=25),
)


def _registro(fatores: tuple[Fator, ...] = FATORES) -> RegistroAnalise:
    return RegistroAnalise(
        score=sum(fator.peso for fator in fatores),
        nivel_risco="MEDIO",
        tipo_input="texto",
        fatores=fatores,
    )


async def _contar(sessao: AsyncSession, modelo: type[Analise] | type[IndicadorRisco]) -> int:
    return await sessao.scalar(select(func.count()).select_from(modelo)) or 0


async def test_grava_analise_com_todos_os_indicadores(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    id_analise = await RepositorioAnalisesPostgres(fabrica_de_sessoes).registrar(_registro())

    async with fabrica_de_sessoes() as sessao:
        analise = await sessao.scalar(
            select(Analise)
            .where(Analise.id == id_analise)
            .options(selectinload(Analise.indicadores))
        )

    assert analise is not None
    assert analise.score_risco == 50
    assert analise.nivel_risco == "MEDIO"
    assert analise.tipo_input == "texto"
    assert analise.created_at is not None
    assert sorted((i.categoria, i.peso) for i in analise.indicadores) == sorted(
        (f.categoria, f.peso) for f in FATORES
    )


async def test_relacao_sem_selectinload_levanta_em_vez_de_fazer_io(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    """lazy="raise": a regra 2 do ADR-0001 é garantida pelo ORM."""
    id_analise = await RepositorioAnalisesPostgres(fabrica_de_sessoes).registrar(_registro())

    async with fabrica_de_sessoes() as sessao:
        analise = await sessao.get_one(Analise, id_analise)
        with pytest.raises(Exception, match="lazy='raise'"):
            _ = analise.indicadores


async def test_apagar_a_analise_apaga_os_indicadores(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    id_analise = await RepositorioAnalisesPostgres(fabrica_de_sessoes).registrar(_registro())

    async with fabrica_de_sessoes() as sessao, sessao.begin():
        # SQL direto, sem passar pelo ORM: quem tem de apagar os filhos é o ON DELETE CASCADE.
        await sessao.execute(text("DELETE FROM analises WHERE id = :id"), {"id": id_analise})

    async with fabrica_de_sessoes() as sessao:
        assert await _contar(sessao, Analise) == 0
        assert await _contar(sessao, IndicadorRisco) == 0


async def test_indicador_que_falha_no_meio_nao_deixa_analise(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    """Invariante 6: nunca análise sem indicador nem conjunto parcial.

    O terceiro fator tem peso 0, que só o CHECK do banco recusa (o `model_construct` pula a
    validação do Pydantic de propósito). Os dois primeiros e a análise têm de sumir junto.
    """
    invalido = Fator.model_construct(
        tipo="texto", categoria="dados_pessoais", descricao="Pede CPF.", peso=0
    )

    with pytest.raises(IntegrityError):
        await RepositorioAnalisesPostgres(fabrica_de_sessoes).registrar(
            _registro((*FATORES[:2], invalido))
        )

    async with fabrica_de_sessoes() as sessao:
        assert await _contar(sessao, Analise) == 0
        assert await _contar(sessao, IndicadorRisco) == 0


async def test_texto_de_entrada_nao_aparece_em_nenhuma_coluna_de_texto(
    fabrica_de_sessoes: async_sessionmaker[AsyncSession],
) -> None:
    """ADR-0006: a análise anônima não guarda a mensagem — nem inteira, nem em pedaços.

    Passa pelo orquestrador, que recebe o texto de verdade. As colunas são lidas do
    `information_schema`, e não listadas à mão: uma coluna de texto criada no futuro entra na
    varredura sozinha. O marcador também está na query da URL, que o ADR-0009 preserva.
    """
    marcador = "XYZZY4242"
    texto = (
        f"URGENTE: sua conta será bloqueada. Faça um PIX para {marcador} e confirme seu CPF "
        f"em http://golpe-exemplo.xyz/pix?email={marcador}"
    )
    orquestrador = OrquestradorAnalise(
        servico=obter_servico_analise(),
        repositorio=RepositorioAnalisesPostgres(fabrica_de_sessoes),
        timeout_s=5.0,
    )

    resposta = await orquestrador.analisar(texto)

    assert resposta.fatores, "a mensagem precisa pontuar, senão o teste não prova nada"
    async with fabrica_de_sessoes() as sessao:
        assert await _contar(sessao, IndicadorRisco) == len(resposta.fatores)
        colunas = (
            await sessao.execute(
                text(
                    "SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE table_name IN ('analises', 'indicadores_risco') "
                    "AND data_type IN ('text', 'character varying')"
                )
            )
        ).all()
        assert colunas
        for tabela, coluna in colunas:
            achados = await sessao.scalar(
                text(f"SELECT count(*) FROM {tabela} WHERE {coluna} LIKE :padrao"),
                {"padrao": f"%{marcador}%"},
            )
            assert achados == 0, f"{tabela}.{coluna} contém trecho da mensagem"
