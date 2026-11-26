"""A regra de privacidade da observabilidade (ADR-0026), de ponta a ponta.

Uma análise com um conteúdo marcado em cada lugar em que a pessoa escreve — a mensagem, o link,
o texto do print, o que ela digitou junto, o e-mail, a senha, o cookie, a query string — e a
marca não pode aparecer em NENHUM log capturado nem no corpo de `/metrics`.

O log é conferido três vezes: o texto que o `caplog` formatou, os atributos crus de cada registro
(o `extra=` dos eventos) e a linha JSON que sairia no terminal.
"""

import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.logs import FormatadorJSON, FormatadorTexto
from tests.conftest import (
    ClienteIAFalso,
    ClienteLeituraFalso,
    RepositorioUsuariosEmMemoria,
    corpo_de_print,
    saida_da_ia,
    saida_da_leitura,
    settings_de_teste,
)
from tests.test_api_analise_cota import _ligar_ia, _ligar_leitura

MARCA = "SEGREDO-DO-TESTE-123"
DOMINIO = "segredo-do-teste-123.xyz"
IP = "203.0.113.77"
TOKEN = "token-de-teste-das-metricas-0123456789"

MENSAGEM = (
    f"URGENTE {MARCA}: sua conta será bloqueada hoje. Faça um PIX de R$ 49,90 e confirme seu "
    f"CPF em https://{DOMINIO}/entrar?c={MARCA}"
)


def _tudo_o_que_foi_logado(caplog: pytest.LogCaptureFixture) -> str:
    # Fora os registros do cliente HTTP do PRÓPRIO teste, que loga a URL que o teste pediu. Ele
    # não existe na aplicação: lá, quem recebe o pedido é o servidor.
    registros = [r for r in caplog.records if not r.name.startswith(("httpx", "httpcore"))]
    assert all(r.name.startswith(("app", "asyncio")) for r in registros), {
        r.name for r in registros
    }
    partes = []
    for registro in registros:
        partes.append(registro.getMessage())
        partes.append(str(registro.__dict__))
        partes.append(FormatadorJSON().format(registro))
        partes.append(FormatadorTexto().format(registro))
    return "\n".join(partes)


def _conferir(texto: str) -> None:
    for proibido in (MARCA, MARCA.lower(), DOMINIO, IP, "maria@exemplo.com", "uma senha boa"):
        assert proibido not in texto


@pytest.fixture
async def navegador(app: FastAPI) -> AsyncClient:
    app.dependency_overrides[get_settings] = lambda: settings_de_teste(metrics_token=TOKEN)
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://teste",
        headers={"X-Forwarded-For": IP, "X-Request-ID": MARCA},
    )


async def _metricas(cliente: AsyncClient) -> str:
    resposta = await cliente.get("/metrics", headers={"Authorization": f"Bearer {TOKEN}"})
    assert resposta.status_code == 200
    return resposta.text


@pytest.mark.parametrize("ia_ligada", [False, True], ids=["so-motor", "com-ia"])
async def test_analise_de_texto_nao_vaza(
    ia_ligada: bool, app: FastAPI, navegador: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    if ia_ligada:
        # A IA devolve a marca no que escreve, como faria ao citar a mensagem.
        _ligar_ia(app, ClienteIAFalso(saida_da_ia(tipo=f"golpe {MARCA}")))
    async with navegador as cliente:
        with caplog.at_level(logging.DEBUG):
            resposta = await cliente.post(f"/api/analises?q={MARCA}", json={"texto": MENSAGEM})
        metricas = await _metricas(cliente)

    assert resposta.status_code == 200
    # A análise aconteceu e foi observada: não é um teste que passa por não haver log.
    assert any(getattr(r, "evento", None) == "analise_concluida" for r in caplog.records)
    assert any(getattr(r, "evento", None) == "requisicao" for r in caplog.records)
    _conferir(_tudo_o_que_foi_logado(caplog))
    _conferir(metricas)


@pytest.mark.parametrize(
    "cliente_ia",
    [
        ClienteIAFalso(erro=RuntimeError(f"a API devolveu o pedido: {MARCA}")),
        ClienteIAFalso(f'{{"nivel_sugerido": "{MARCA}"}}'),
        ClienteIAFalso(motivo_parada="refusal"),
    ],
    ids=["erro-com-o-texto", "json-fora-do-contrato", "recusa"],
)
async def test_falha_da_ia_nao_vaza(
    cliente_ia: ClienteIAFalso,
    app: FastAPI,
    navegador: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """O erro de validação do Pydantic cita o valor recebido; a exceção da API pode citar o
    pedido. Do erro, o log leva só o tipo."""
    _ligar_ia(app, cliente_ia)
    async with navegador as cliente:
        with caplog.at_level(logging.DEBUG):
            resposta = await cliente.post("/api/analises", json={"texto": MENSAGEM})
        metricas = await _metricas(cliente)

    assert resposta.status_code == 200
    assert any(getattr(r, "evento", None) == "ia_falhou" for r in caplog.records)
    _conferir(_tudo_o_que_foi_logado(caplog))
    _conferir(metricas)


async def test_analise_de_print_nao_vaza(
    app: FastAPI, navegador: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    _ligar_ia(app, ClienteIAFalso(saida_da_ia(tipo=f"golpe {MARCA}")))
    _ligar_leitura(
        app,
        ClienteLeituraFalso(saida_da_leitura([("contato", MENSAGEM), ("pessoa", f"eu: {MARCA}")])),
    )
    corpo = corpo_de_print(texto=f"recebi isto {MARCA}")
    async with navegador as cliente:
        with caplog.at_level(logging.DEBUG):
            resposta = await cliente.post("/api/analises/imagem", json=corpo)
        metricas = await _metricas(cliente)

    assert resposta.status_code == 200
    assert any(getattr(r, "evento", None) == "analise_concluida" for r in caplog.records)
    logado = _tudo_o_que_foi_logado(caplog)
    _conferir(logado)
    _conferir(metricas)
    # Nem um pedaço da imagem.
    assert str(corpo["imagem_base64"])[:40] not in logado


async def test_conta_e_login_nao_vazam(
    navegador: AsyncClient,
    usuarios: RepositorioUsuariosEmMemoria,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cadastro = {"nome": f"Maria {MARCA}", "email": "maria@exemplo.com", "senha": "uma senha boa"}
    async with navegador as cliente:
        with caplog.at_level(logging.DEBUG):
            criada = await cliente.post("/api/auth/cadastro", json=cadastro)
            await cliente.post(
                "/api/auth/login", json={"email": "maria@exemplo.com", "senha": MARCA}
            )
            await cliente.post("/api/analises", json={"texto": MENSAGEM})
        sessao = criada.cookies.get("__Host-vs_sessao")
        metricas = await _metricas(cliente)

    assert criada.status_code == 201
    assert sessao
    assert any(getattr(r, "evento", None) == "login_falhou" for r in caplog.records)
    logado = _tudo_o_que_foi_logado(caplog)
    _conferir(logado)
    _conferir(metricas)
    # Nem o cookie da sessão, nem o id da conta.
    assert sessao not in logado
    id_da_conta = usuarios.credenciais["maria@exemplo.com"].usuario.id
    assert str(id_da_conta) not in logado
    assert id_da_conta.hex not in logado
