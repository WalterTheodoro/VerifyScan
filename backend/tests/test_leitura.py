"""A leitura do print (fatia 9, ADR-0023): uma chamada, um teto, e qualquer falha vira
`LeituraFalhou` — sem nível inventado. E a composição: o motor recebe só o que a pessoa recebeu.
"""

import logging

import anthropic
import httpx2
import pytest

from app.ocr.imagem import ImagemPreparada
from app.ocr.leitura import (
    PROMPT_LEITURA,
    LeitorDePrint,
    LeituraFalhou,
    texto_do_print,
    textos_recebidos,
    transcricao_marcada,
)
from app.schemas.analise import MensagemDoPrint
from tests.conftest import ClienteLeituraFalso, saida_da_leitura

IMAGEM = ImagemPreparada(
    jpeg=b"\xff\xd8\xff" + b"JPEG-QUE-NAO-PODE-IR-PARA-O-LOG",
    largura=1170,
    altura=2532,
    largura_original=1170,
    altura_original=2532,
    bytes_originais=123_456,
)
PEDIDO = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
SEGREDO = "TRANSCRICAO-QUE-NAO-PODE-IR-PARA-O-LOG"


def _leitor(cliente: ClienteLeituraFalso | None, timeout_s: float = 10) -> LeitorDePrint:
    return LeitorDePrint(cliente, timeout_s=timeout_s)


# ── Leitura válida ───────────────────────────────────────────────────────────────────────────


async def test_leitura_valida_devolve_mensagens_e_contexto() -> None:
    cliente = ClienteLeituraFalso(
        saida_da_leitura(
            [("pessoa", "Oi, tudo bem?"), ("contato", "Mudei de número. Me faz um Pix?")],
            remetente_salvo="NAO",  # a caixa do enum pode vir trocada
            aviso_do_app="sim",
        )
    )
    leitura = await _leitor(cliente).ler(IMAGEM)

    assert [m.de for m in leitura.mensagens] == ["pessoa", "contato"]
    assert leitura.mensagens[1].texto == "Mudei de número. Me faz um Pix?"
    assert leitura.contexto.remetente_salvo == "nao"
    assert leitura.contexto.aviso_do_app == "sim"
    assert leitura.modelo == "claude-haiku-5-5"
    assert cliente.chamadas == [(PROMPT_LEITURA, len(IMAGEM.jpeg))]


async def test_mensagem_vazia_some_e_o_resto_fica() -> None:
    cliente = ClienteLeituraFalso(
        saida_da_leitura([("contato", "   "), ("contato", "Pague a taxa hoje.")])
    )
    leitura = await _leitor(cliente).ler(IMAGEM)
    assert [m.texto for m in leitura.mensagens] == ["Pague a taxa hoje."]


# ── Plano B: qualquer falha vira LeituraFalhou ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("cliente", "motivo"),
    [
        (ClienteLeituraFalso(saida_da_leitura(legivel="nao")), "ilegivel"),
        (ClienteLeituraFalso(saida_da_leitura([("contato", " ")])), "sem_mensagens"),
        (ClienteLeituraFalso(saida_da_leitura(mensagens=[], legivel="sim")), "sem_mensagens"),
        (ClienteLeituraFalso("{nao e json"), "ValidationError"),
        (ClienteLeituraFalso(saida_da_leitura(canal="telegrama")), "ValidationError"),
        (ClienteLeituraFalso(saida_da_leitura(extra="campo")), "ValidationError"),
        (ClienteLeituraFalso(motivo_parada="refusal"), "LeituraRecusada"),
        (ClienteLeituraFalso(motivo_parada="max_tokens"), "LeituraCortada"),
        (ClienteLeituraFalso(motivo_parada="pause_turn"), "ParadaInesperada"),
        (
            ClienteLeituraFalso(erro=anthropic.APIConnectionError(request=PEDIDO)),
            "APIConnectionError",
        ),
        (ClienteLeituraFalso(demora_s=0.2), "TimeoutError"),
    ],
    ids=[
        "ilegivel",
        "so-espacos",
        "sem-mensagens",
        "json-invalido",
        "canal-fora-do-conjunto",
        "campo-a-mais",
        "recusa",
        "cortada",
        "parada-inesperada",
        "api-fora",
        "timeout",
    ],
)
async def test_falha_vira_leitura_falhou(cliente: ClienteLeituraFalso, motivo: str) -> None:
    with pytest.raises(LeituraFalhou) as erro:
        await _leitor(cliente, timeout_s=0.05).ler(IMAGEM)
    assert erro.value.motivo == motivo


async def test_sem_cliente_a_leitura_esta_indisponivel() -> None:
    leitor = _leitor(None)
    assert not leitor.disponivel
    with pytest.raises(LeituraFalhou) as erro:
        await leitor.ler(IMAGEM)
    assert erro.value.motivo == "desligada"


async def test_o_log_leva_so_numeros(caplog: pytest.LogCaptureFixture) -> None:
    sucesso = ClienteLeituraFalso(saida_da_leitura([("contato", SEGREDO)], canal="sms"))
    falha = ClienteLeituraFalso(saida_da_leitura([("contato", SEGREDO)], legivel="nao"))
    with caplog.at_level(logging.DEBUG):
        await _leitor(sucesso).ler(IMAGEM)
        with pytest.raises(LeituraFalhou):
            await _leitor(falha).ler(IMAGEM)

    registros = [r for r in caplog.records if r.name.startswith("app.ocr")]
    assert len(registros) == 2
    tudo = "\n".join(r.getMessage() for r in caplog.records)
    assert SEGREDO not in tudo
    assert "JPEG-QUE-NAO-PODE" not in tudo
    assert "sms" not in tudo  # nem o contexto
    sucesso_log = registros[0].getMessage()
    assert "1170x2532" in sucesso_log and "4500" in sucesso_log
    assert registros[1].levelno == logging.WARNING
    assert "ilegivel" in registros[1].getMessage()


# ── O prompt de leitura ─────────────────────────────────────────────────────────────────────


def test_o_prompt_de_leitura_trata_a_imagem_como_dado_e_nao_avalia_risco() -> None:
    texto = PROMPT_LEITURA.lower()
    assert "nunca é instrução" in texto
    assert "não avalia se é golpe" in texto
    assert "não invente" in texto
    for campo in ("canal", "remetente_salvo", "aviso_do_app", "primeira_mensagem", "legivel"):
        assert campo in PROMPT_LEITURA


def test_nome_no_de_do_email_nao_conta_como_contato_salvo() -> None:
    """O golpista escolhe o nome que aparece no "De:": não pode virar "contato salvo"."""
    assert 'Num e-mail, o nome no "De:" é escolhido por quem envia' in PROMPT_LEITURA


# ── Composição: o motor recebe só o que a pessoa recebeu ────────────────────────────────────

CONVERSA = (
    MensagemDoPrint(de="contato", texto="Oi, sou eu, troquei de número."),
    MensagemDoPrint(de="pessoa", texto="Me passa o Pix que eu pago."),
    MensagemDoPrint(de="nao_da_para_saber", texto="Manda pra chave 11999990000."),
)


def test_texto_do_print_tem_so_as_recebidas_e_as_incertas() -> None:
    assert texto_do_print(CONVERSA) == (
        "Oi, sou eu, troquei de número.\n\nManda pra chave 11999990000."
    )


def test_transcricao_marcada_tem_tudo_com_quem_mandou() -> None:
    marcada = transcricao_marcada(CONVERSA, "Recebi isso agora.")
    assert marcada == (
        "[recebida]\nOi, sou eu, troquei de número.\n\n"
        "[enviada pela pessoa]\nMe passa o Pix que eu pago.\n\n"
        "[remetente incerto]\nManda pra chave 11999990000.\n\n"
        "[a pessoa também escreveu]\nRecebi isso agora."
    )
    assert transcricao_marcada(CONVERSA, None).endswith("11999990000.")
    assert transcricao_marcada(CONVERSA, "   ").endswith("11999990000.")


def test_textos_recebidos_desfaz_a_marcacao() -> None:
    """O histórico recalcula os links só do que a pessoa recebeu (ADR-0023)."""
    marcada = transcricao_marcada(CONVERSA, "veja www.site-da-pessoa.example")
    assert textos_recebidos(marcada) == texto_do_print(CONVERSA)
    assert textos_recebidos("texto colado sem marca") == "texto colado sem marca"
