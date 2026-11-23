"""Sentry (ADR-0026): só liga com DSN, e nada de quem pediu sai do processo.

Nenhum teste aqui fala com a rede. O envio é trocado por um transporte que guarda os envelopes
em memória; o DSN é falso e nunca é resolvido.
"""

import json
from collections.abc import Iterator
from typing import Any, ClassVar

import pytest
import sentry_sdk
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport

from app.api.deps import obter_orquestrador
from app.core import sentry as modulo
from app.core.sentry import CABECALHOS_PROIBIDOS, COLETA, iniciar_sentry, limpar_evento
from app.main import criar_app
from tests.conftest import corpo_de_print, settings_de_teste

MARCA = "SEGREDO-DO-TESTE-123"
DSN_FALSO = "https://chavepublica@o0.ingest.exemplo.invalid/1"


# ─── só liga com DSN ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def init_espiado(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Troca o `sentry_sdk.init` por um que só anota os argumentos: nada é ligado de verdade."""
    chamadas: list[dict[str, Any]] = []
    monkeypatch.setattr(modulo.sentry_sdk, "init", lambda **opcoes: chamadas.append(opcoes))
    return chamadas


def test_sem_dsn_nao_inicializa(init_espiado: list[dict[str, Any]]) -> None:
    assert iniciar_sentry(settings_de_teste()) is False
    assert iniciar_sentry(settings_de_teste(sentry_dsn="")) is False
    assert init_espiado == []


def test_a_app_de_teste_sobe_sem_sentry(
    init_espiado: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.setattr("app.main.get_settings", lambda: settings_de_teste())

    criar_app()

    assert init_espiado == []


def test_com_dsn_liga_com_a_configuracao_obrigatoria(init_espiado: list[dict[str, Any]]) -> None:
    ligou = iniciar_sentry(
        settings_de_teste(sentry_dsn=DSN_FALSO, sentry_environment="producao", app_version="1.2.3")
    )

    assert ligou is True
    [opcoes] = init_espiado
    assert opcoes["dsn"] == DSN_FALSO
    # O `send_default_pii` ficou obsoleto: quem diz o que o SDK coleta é o `data_collection`.
    assert "send_default_pii" not in opcoes
    assert opcoes["data_collection"] is COLETA
    assert opcoes["max_request_body_size"] == "never"
    assert opcoes["include_local_variables"] is False
    assert opcoes["traces_sample_rate"] == 0.1
    assert opcoes["environment"] == "producao"
    assert opcoes["release"] == "1.2.3"
    assert opcoes["before_send"] is limpar_evento
    assert opcoes["before_send_transaction"] is limpar_evento
    # A integração da Anthropic liga sozinha e captura as exceções da chamada: fica de fora.
    assert opcoes["auto_enabling_integrations"] is False
    assert opcoes["max_breadcrumbs"] == 0


def test_nenhuma_categoria_de_coleta_fica_ligada() -> None:
    assert COLETA["user_info"] is False
    assert COLETA["cookies"] == {"mode": "off"}
    assert COLETA["url_query_params"] == {"mode": "off"}
    assert COLETA["http_bodies"] == []
    assert COLETA["http_headers"]["request"]["mode"] == "allowlist"
    assert COLETA["graphql"] == {"document": False, "variables": False}
    assert COLETA["gen_ai"] == {"inputs": False, "outputs": False}
    assert COLETA["database_query_data"] is False
    assert COLETA["queues"] is False
    assert COLETA["stack_frame_variables"] is False
    # Nenhum cabeçalho proibido está entre os que podem sair com o valor.
    permitidos = set(COLETA["http_headers"]["request"]["terms"])
    assert permitidos.isdisjoint(CABECALHOS_PROIBIDOS)


def test_toda_categoria_que_o_sdk_conhece_esta_declarada() -> None:
    """Categoria omitida no `data_collection` é categoria COLETADA. Se uma versão nova do SDK
    trouxer outra, este teste falha até ela ser escrita em `COLETA`."""
    from sentry_sdk.data_collection import _resolve_explicit

    do_sdk = set(_resolve_explicit({})) - {"provided_by_user"}

    assert do_sdk == set(COLETA)


def test_ligar_de_verdade_nao_usa_opcao_obsoleta() -> None:
    """Com o SDK de verdade e o envio em memória: nenhum aviso de depreciação na inicialização."""
    import warnings

    init_de_verdade = sentry_sdk.init
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        with pytest.MonkeyPatch.context() as troca:
            troca.setattr(
                modulo.sentry_sdk,
                "init",
                lambda **opcoes: init_de_verdade(**opcoes, transport=TransporteEmMemoria),
            )
            try:
                assert iniciar_sentry(settings_de_teste(sentry_dsn=DSN_FALSO)) is True
            finally:
                init_de_verdade()


@pytest.mark.parametrize(
    ("valores", "esperada"),
    [
        ({"app_version": "1.2.3", "render_git_commit": "abc123"}, "1.2.3"),
        ({"render_git_commit": "abc123"}, "abc123"),
        ({}, None),
    ],
    ids=["app-version", "commit-do-render", "nada"],
)
def test_release(
    valores: dict[str, str], esperada: str | None, init_espiado: list[dict[str, Any]]
) -> None:
    iniciar_sentry(settings_de_teste(sentry_dsn=DSN_FALSO, **valores))

    assert init_espiado[0]["release"] == esperada


def test_taxa_de_amostragem_vem_da_variavel(init_espiado: list[dict[str, Any]]) -> None:
    iniciar_sentry(settings_de_teste(sentry_dsn=DSN_FALSO, sentry_traces_sample_rate=0.5))

    assert init_espiado[0]["traces_sample_rate"] == 0.5


def test_taxa_fora_de_zero_a_um_nao_sobe() -> None:
    with pytest.raises(ValueError):
        settings_de_teste(sentry_traces_sample_rate=1.5)


# ─── a limpeza, com um evento falso ───────────────────────────────────────────────────────


def _evento_falso() -> dict[str, Any]:
    """Um evento com a marca em todo campo proibido, no formato que o SDK monta."""
    return {
        "transaction": f"/api/historico/{MARCA}",
        "transaction_info": {"source": "url"},
        "message": f"mensagem {MARCA}",
        "logentry": {"message": f"log {MARCA}"},
        "user": {"id": MARCA, "ip_address": "203.0.113.9", "email": "maria@exemplo.com"},
        "request": {
            "method": "POST",
            "url": f"https://verifyscan.exemplo/api/historico/{MARCA}",
            "query_string": f"q={MARCA}",
            "data": {"texto": MARCA, "imagem_base64": MARCA},
            "cookies": {"vs_sessao": MARCA},
            "env": {"REMOTE_ADDR": "203.0.113.9"},
            "headers": {
                "Authorization": f"Bearer {MARCA}",
                "Cookie": f"vs_sessao={MARCA}",
                "X-VerifyScan-IP": "203.0.113.9",
                "X-VerifyScan-Segredo": MARCA,
                "X-Forwarded-For": "203.0.113.9, 198.51.100.7",
                "x-real-ip": "203.0.113.9",
                "Forwarded": "for=203.0.113.9",
                "Set-Cookie": f"vs_sessao={MARCA}",
                "Content-Type": "application/json",
                "X-Request-ID": "3f0c2b0e-8f55-4d0a-9d0e-0a1b2c3d4e5f",
            },
        },
        "breadcrumbs": {"values": [{"category": "log", "message": f"rastro {MARCA}"}]},
        "exception": {
            "values": [
                {
                    "type": "ValidationError",
                    "value": f"1 validation error [input_value='{MARCA}']",
                    "stacktrace": {
                        "frames": [
                            {
                                "filename": "app/services/analise.py",
                                "function": "analisar",
                                "lineno": 10,
                                "vars": {"texto": MARCA},
                            }
                        ]
                    },
                }
            ]
        },
    }


def test_limpar_evento_remove_todos_os_campos_proibidos() -> None:
    limpo = limpar_evento(_evento_falso())

    serializado = json.dumps(limpo)
    assert MARCA not in serializado
    assert "203.0.113.9" not in serializado
    assert "maria@exemplo.com" not in serializado
    pedido = limpo["request"]
    for campo in ("data", "cookies", "query_string", "env", "url"):
        assert campo not in pedido
    assert {nome.lower() for nome in pedido["headers"]}.isdisjoint(CABECALHOS_PROIBIDOS)
    for campo in ("user", "breadcrumbs", "message", "logentry"):
        assert campo not in limpo


def test_limpar_evento_remove_o_extra() -> None:
    """Com o `data_collection`, o SDK deixa de aplicar o `EventScrubber` dele, que mascarava as
    chaves com cara de segredo dentro do `extra`. O `limpar_evento` é a única camada: o `extra`
    sai inteiro."""
    limpo = limpar_evento({"level": "error", "extra": {"password": "x", "texto": MARCA}})

    assert "extra" not in limpo
    assert limpo == {"level": "error"}


def test_limpar_evento_remove_o_data_de_cada_trecho() -> None:
    """Os atributos dos trechos de desempenho são onde uma integração anota endereço, query
    string e cabeçalhos. O scrubber do SDK os mascarava; agora saem inteiros."""
    transacao = {
        "type": "transaction",
        "transaction": "/api/analises",
        "transaction_info": {"source": "route"},
        "spans": [
            {
                "op": "http.client",
                "description": "POST",
                "span_id": "a1b2c3d4e5f60718",
                "status": "ok",
                "data": {"http.query": MARCA, "password": MARCA, "client.address": "203.0.113.9"},
            },
            {"op": "middleware.starlette", "description": "CORSMiddleware"},
        ],
    }

    limpa = limpar_evento(transacao)

    assert MARCA not in json.dumps(limpa)
    assert "203.0.113.9" not in json.dumps(limpa)
    # O que identifica o trecho e diz como ele terminou continua.
    assert limpa["spans"] == [
        {"op": "http.client", "description": "POST", "span_id": "a1b2c3d4e5f60718", "status": "ok"},
        {"op": "middleware.starlette", "description": "CORSMiddleware"},
    ]


def test_limpar_evento_remove_o_data_do_contexto_do_trace() -> None:
    evento = {
        "contexts": {
            "trace": {
                "trace_id": "0af7651916cd43dd8448eb211c80319c",
                "span_id": "b7ad6b7169203331",
                "op": "http.server",
                "data": {"url.query": MARCA, "client.address": "203.0.113.9"},
            },
            "runtime": {"name": "CPython"},
        },
        "tags": {"ambiente": "teste"},
    }

    limpo = limpar_evento(evento)

    assert MARCA not in json.dumps(limpo)
    assert "203.0.113.9" not in json.dumps(limpo)
    # Os ids que ligam o erro à transação ficam, e o resto do `contexts` e as `tags` também.
    assert limpo["contexts"] == {
        "trace": {
            "trace_id": "0af7651916cd43dd8448eb211c80319c",
            "span_id": "b7ad6b7169203331",
            "op": "http.server",
        },
        "runtime": {"name": "CPython"},
    }
    assert limpo["tags"] == {"ambiente": "teste"}


def test_o_sdk_ficou_sem_o_scrubber_dele(sentry_em_memoria: list[Envelope]) -> None:
    """Registra o fato em que a decisão se apoia (ADR-0026). Se uma versão nova do SDK voltar a
    ligar o scrubber junto com o `data_collection`, este teste falha e o ADR pode ser revisto."""
    assert sentry_sdk.get_client().options["event_scrubber"] is None


def test_limpar_evento_deixa_o_que_serve_para_depurar() -> None:
    limpo = limpar_evento(_evento_falso())

    assert limpo["request"]["method"] == "POST"
    assert limpo["request"]["headers"] == {
        "Content-Type": "application/json",
        "X-Request-ID": "3f0c2b0e-8f55-4d0a-9d0e-0a1b2c3d4e5f",
    }
    [excecao] = limpo["exception"]["values"]
    assert excecao["type"] == "ValidationError"
    assert "value" not in excecao
    assert excecao["stacktrace"]["frames"] == [
        {"filename": "app/services/analise.py", "function": "analisar", "lineno": 10}
    ]


def test_transacao_sem_rota_perde_o_caminho_cru() -> None:
    assert limpar_evento(_evento_falso())["transaction"] == "nao_mapeada"


def test_transacao_com_rota_fica_com_o_template() -> None:
    evento = {
        "transaction": "/api/historico/{analise_id}",
        "transaction_info": {"source": "route"},
    }

    assert limpar_evento(evento)["transaction"] == "/api/historico/{analise_id}"


def test_evento_sem_pedido_nem_excecao_passa() -> None:
    assert limpar_evento({"level": "error"}) == {"level": "error"}


def test_cabecalhos_do_proxy_estao_na_lista() -> None:
    """Os mesmos nomes de `app/core/ip.py`: se o proxy ganhar outro cabeçalho, este teste lembra."""
    from app.core import ip

    do_proxy = {
        valor.lower()
        for nome, valor in vars(ip).items()
        if nome.startswith("CABECALHO") and isinstance(valor, str)
    }
    assert do_proxy
    assert do_proxy <= CABECALHOS_PROIBIDOS


# ─── de ponta a ponta, com o SDK de verdade e o envio em memória ──────────────────────────


class TransporteEmMemoria(Transport):
    """Guarda os envelopes em vez de enviar. Nenhuma conexão é aberta."""

    enviados: ClassVar[list[Envelope]] = []

    def capture_envelope(self, envelope: Envelope) -> None:
        TransporteEmMemoria.enviados.append(envelope)


@pytest.fixture
def sentry_em_memoria(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[Envelope]]:
    """Liga o SDK com a NOSSA configuração (a de `iniciar_sentry`), trocando só o transporte."""
    TransporteEmMemoria.enviados = []
    init_de_verdade = sentry_sdk.init
    monkeypatch.setattr(
        modulo.sentry_sdk,
        "init",
        lambda **opcoes: init_de_verdade(**opcoes, transport=TransporteEmMemoria),
    )
    iniciar_sentry(settings_de_teste(sentry_dsn=DSN_FALSO, sentry_traces_sample_rate=1.0))
    try:
        yield TransporteEmMemoria.enviados
    finally:
        # Sem DSN: o cliente volta a ficar desligado para os outros testes.
        init_de_verdade()


class OrquestradorQuebrado:
    """Levanta com a marca na mensagem da exceção e numa variável local, como faria um erro de
    validação no meio da análise."""

    async def analisar(self, texto: str, *args: object) -> None:
        copia_local = texto  # noqa: F841 — existe para provar que variável local não sai
        raise RuntimeError(f"valor recebido: {texto}")

    async def analisar_print(self, imagem: bytes, texto: str | None, *args: object) -> None:
        raise RuntimeError(f"valor recebido: {texto}")


def _tudo_o_que_saiu(envelopes: list[Envelope]) -> str:
    return "\n".join(
        json.dumps(item.payload.json or {}, default=str) + str(item.payload.bytes or b"")
        for envelope in envelopes
        for item in envelope.items
    )


def _tipos(envelopes: list[Envelope]) -> set[str | None]:
    return {item.type for envelope in envelopes for item in envelope.items}


@pytest.fixture
async def cliente_que_nao_levanta(app: FastAPI) -> AsyncClient:
    app.dependency_overrides[obter_orquestrador] = lambda: OrquestradorQuebrado()
    transporte = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transporte, base_url="https://teste")


async def test_erro_na_analise_de_texto_chega_ao_sentry_sem_o_conteudo(
    sentry_em_memoria: list[Envelope], cliente_que_nao_levanta: AsyncClient
) -> None:
    async with cliente_que_nao_levanta as cliente:
        resposta = await cliente.post(
            f"/api/analises?q={MARCA}",
            json={"texto": f"mensagem com {MARCA}"},
            headers={
                "Cookie": f"vs_sessao={MARCA}",
                "Authorization": f"Bearer {MARCA}",
                "X-Forwarded-For": "203.0.113.9",
                "X-VerifyScan-IP": "203.0.113.9",
                "X-VerifyScan-Segredo": MARCA,
            },
        )
    sentry_sdk.flush()

    assert resposta.status_code == 500
    # O erro chegou, e a transação também (amostragem em 100% neste teste).
    assert {"event", "transaction"} <= _tipos(sentry_em_memoria)
    saiu = _tudo_o_que_saiu(sentry_em_memoria)
    assert "RuntimeError" in saiu
    assert MARCA not in saiu
    assert "203.0.113.9" not in saiu


async def test_erro_na_analise_de_print_chega_ao_sentry_sem_a_imagem(
    sentry_em_memoria: list[Envelope], cliente_que_nao_levanta: AsyncClient
) -> None:
    corpo = corpo_de_print(texto=f"contexto com {MARCA}")
    async with cliente_que_nao_levanta as cliente:
        resposta = await cliente.post("/api/analises/imagem", json=corpo)
    sentry_sdk.flush()

    assert resposta.status_code in (500, 503)
    saiu = _tudo_o_que_saiu(sentry_em_memoria)
    assert MARCA not in saiu
    assert str(corpo["imagem_base64"])[:40] not in saiu


def test_extra_anexado_pelo_codigo_nao_chega_ao_sentry(
    sentry_em_memoria: list[Envelope],
) -> None:
    """De ponta a ponta: um `set_extra` futuro, com chave sensível ou não, sai sem o conteúdo."""
    with sentry_sdk.isolation_scope():
        sentry_sdk.set_extra("password", MARCA)
        sentry_sdk.set_extra("mensagem_analisada", MARCA)
        sentry_sdk.capture_exception(RuntimeError("falhou"))
    sentry_sdk.flush()

    assert "event" in _tipos(sentry_em_memoria)
    saiu = _tudo_o_que_saiu(sentry_em_memoria)
    assert "RuntimeError" in saiu
    assert MARCA not in saiu


async def test_caminho_que_nao_existe_nao_vira_nome_de_transacao(
    sentry_em_memoria: list[Envelope], app: FastAPI
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://teste") as cliente:
        await cliente.get(f"/{MARCA}/qualquer")
    sentry_sdk.flush()

    assert MARCA not in _tudo_o_que_saiu(sentry_em_memoria)
