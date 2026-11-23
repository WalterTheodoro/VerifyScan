"""Logs estruturados (ADR-0026): uma linha JSON por log, com o id da requisição, e nunca a
mensagem de uma exceção — erro de validação e erro de driver citam o que a pessoa mandou."""

import io
import json
import logging

import pytest

from app.core.logs import (
    FormatadorJSON,
    FormatadorTexto,
    configurar_logs,
    evento,
    request_id_atual,
)

MARCA = "SEGREDO-DO-TESTE-123"


def _registro(
    mensagem: str = "Senha trocada",
    *,
    nivel: int = logging.INFO,
    extra: dict[str, object] | None = None,
    exc_info: object = None,
) -> logging.LogRecord:
    registro = logging.LogRecord("app.teste", nivel, __file__, 1, mensagem, None, exc_info)  # type: ignore[arg-type]
    for chave, valor in (extra or {}).items():
        setattr(registro, chave, valor)
    return registro


def _excecao_com_a_marca() -> tuple[type[BaseException], BaseException, object]:
    try:
        raise ValueError(f"valor recebido: {MARCA}")
    except ValueError as exc:
        return type(exc), exc, exc.__traceback__


def test_json_valido_com_os_campos_fixos() -> None:
    linha = FormatadorJSON().format(_registro())

    dados = json.loads(linha)
    assert "\n" not in linha
    assert dados["nivel"] == "INFO"
    assert dados["evento"] == "log"
    assert dados["mensagem"] == "Senha trocada"
    assert dados["logger"] == "app.teste"
    assert dados["request_id"] is None
    # ISO 8601 em UTC: ordenável como texto e sem depender do fuso da máquina.
    assert dados["ts"].endswith("+00:00")


def test_o_request_id_vem_do_contexto() -> None:
    marca = request_id_atual.set("3f0c2b0e-8f55-4d0a-9d0e-0a1b2c3d4e5f")
    try:
        dados = json.loads(FormatadorJSON().format(_registro()))
    finally:
        request_id_atual.reset(marca)

    assert dados["request_id"] == "3f0c2b0e-8f55-4d0a-9d0e-0a1b2c3d4e5f"


def test_evento_leva_o_nome_e_os_campos() -> None:
    registro = _registro(
        "analise_concluida", extra=evento("analise_concluida", tipo="texto", ia_usada=False)
    )

    dados = json.loads(FormatadorJSON().format(registro))

    assert dados["evento"] == "analise_concluida"
    assert dados["tipo"] == "texto"
    assert dados["ia_usada"] is False
    # Mensagem igual ao nome do evento não é repetida.
    assert "mensagem" not in dados


def test_campo_do_evento_nao_troca_um_campo_fixo() -> None:
    registro = _registro(extra=evento("x", nivel="ALTO", request_id="forjado", ts="ontem"))

    dados = json.loads(FormatadorJSON().format(registro))

    assert dados["nivel"] == "INFO"
    assert dados["request_id"] is None
    assert dados["ts"] != "ontem"


@pytest.mark.parametrize("formatador", [FormatadorJSON(), FormatadorTexto()])
def test_excecao_sai_com_tipo_e_pilha_sem_a_mensagem(formatador: logging.Formatter) -> None:
    linha = formatador.format(_registro("Falhou", exc_info=_excecao_com_a_marca()))

    assert MARCA not in linha
    assert "ValueError" in linha
    # arquivo:linha:função de onde a exceção saiu, sem a linha de código.
    assert "test_logs.py" in linha
    assert "_excecao_com_a_marca" in linha
    assert "raise ValueError" not in linha


def test_pilha_no_json_e_uma_lista_de_arquivo_linha_funcao() -> None:
    dados = json.loads(
        FormatadorJSON().format(_registro("Falhou", exc_info=_excecao_com_a_marca()))
    )

    assert dados["erro"] == "ValueError"
    arquivo, linha, funcao = dados["pilha"][-1].rsplit(":", 2)
    assert arquivo.endswith("test_logs.py")
    assert linha.isdigit()
    assert funcao == "_excecao_com_a_marca"


def test_texto_mostra_o_evento_e_os_campos() -> None:
    registro = _registro("Login recusado", extra=evento("login_falhou", motivo="credenciais"))

    linha = FormatadorTexto().format(registro)

    assert linha.startswith("INFO app.teste: Login recusado")
    assert "login_falhou" in linha
    assert "motivo=credenciais" in linha


@pytest.fixture
def logger_do_app() -> object:
    """Devolve o logger `app` ao estado anterior: o `configurar_logs` mexe num objeto global."""
    logger = logging.getLogger("app")
    servidor = logging.getLogger("uvicorn")
    antes = (logger.level, list(logger.handlers), list(servidor.handlers), servidor.propagate)
    yield logger
    logger.setLevel(antes[0])
    logger.handlers[:] = antes[1]
    servidor.handlers[:] = antes[2]
    servidor.propagate = antes[3]


def _saida_de(logger: logging.Logger) -> io.StringIO:
    """Troca o destino do handler do app por um buffer, para ler o que sairia no terminal."""
    saida = io.StringIO()
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.setStream(saida)
    return saida


def test_configurar_logs_em_json_por_padrao(logger_do_app: logging.Logger) -> None:
    logger_do_app.handlers.clear()
    configurar_logs("INFO")
    saida = _saida_de(logger_do_app)

    logging.getLogger("app.teste").info("Senha trocada")

    assert json.loads(saida.getvalue())["mensagem"] == "Senha trocada"


def test_configurar_logs_em_texto(logger_do_app: logging.Logger) -> None:
    logger_do_app.handlers.clear()
    configurar_logs("INFO", "texto")
    saida = _saida_de(logger_do_app)

    logging.getLogger("app.teste").info("Senha trocada")

    assert saida.getvalue().strip() == "INFO app.teste: Senha trocada"


def test_configurar_de_novo_troca_o_formato_sem_empilhar_handler(
    logger_do_app: logging.Logger,
) -> None:
    logger_do_app.handlers.clear()
    configurar_logs("INFO", "texto")
    configurar_logs("INFO", "json")
    saida = _saida_de(logger_do_app)

    logging.getLogger("app.teste").info("Senha trocada")

    assert len(saida.getvalue().strip().splitlines()) == 1
    assert json.loads(saida.getvalue())["evento"] == "log"


def test_log_level_decide_o_que_sai(logger_do_app: logging.Logger) -> None:
    logger_do_app.handlers.clear()
    configurar_logs("WARNING")
    saida = _saida_de(logger_do_app)

    logging.getLogger("app.teste").info("não sai")
    logging.getLogger("app.teste").warning("sai")

    assert [json.loads(linha)["mensagem"] for linha in saida.getvalue().splitlines()] == ["sai"]


def test_o_erro_que_o_uvicorn_loga_passa_pelo_mesmo_formatador(
    logger_do_app: logging.Logger,
) -> None:
    """Numa exceção não tratada, o uvicorn loga o traceback inteiro, com a mensagem da exceção.
    Com o handler do app no logger dele, sai só o tipo e a pilha."""
    logger_do_app.handlers.clear()
    configurar_logs("INFO")
    saida = _saida_de(logger_do_app)

    logging.getLogger("uvicorn.error").error(
        "Exception in ASGI application", exc_info=_excecao_com_a_marca()
    )

    dados = json.loads(saida.getvalue())
    assert dados["erro"] == "ValueError"
    assert dados["logger"] == "uvicorn.error"
    assert MARCA not in saida.getvalue()
