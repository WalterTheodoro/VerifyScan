"""POST /api/analises — a fatia vertical da Fase 1: texto entra, nível de risco sai.

Sem OCR, sem API externa, sem IA e sem login. As duas flags de degradação já existem no
contrato e valem `false` aqui: quem as liga são as Fases 4 e 7, e o contrato não muda por isso.
"""

from time import perf_counter

from httpx import AsyncClient

from app.core.config import get_settings

# A mensagem do Gate 1. Dispara urgência (+10), ameaça de bloqueio (+15), solicitação
# financeira (+25) e dados pessoais (+25) — 75, portanto ALTO.
GOLPE_DE_PIX = (
    "URGENTE: sua conta será bloqueada hoje. Faça um PIX de R$ 49,90 para regularizar "
    "e confirme seu CPF em bb-regularize.xyz"
)


async def test_golpe_de_pix_da_alto_com_os_fatores(cliente: AsyncClient) -> None:
    resposta = await cliente.post("/api/analises", json={"texto": GOLPE_DE_PIX})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["nivel_risco"] == "ALTO"
    assert corpo["score"] == 75
    assert {fator["categoria"] for fator in corpo["fatores"]} == {
        "urgencia",
        "ameaca_bloqueio",
        "solicitacao_financeira",
        "dados_pessoais",
    }


async def test_resposta_traz_as_urls_canonicas(cliente: AsyncClient) -> None:
    """Campo populado desde a Fase 1, embora só a Fase 3 vá pontuar em cima dele."""
    resposta = await cliente.post("/api/analises", json={"texto": GOLPE_DE_PIX})

    assert resposta.json()["urls_analisadas"] == ["http://bb-regularize.xyz/"]


async def test_flags_de_degradacao_existem_e_sao_falsas(cliente: AsyncClient) -> None:
    corpo = (await cliente.post("/api/analises", json={"texto": GOLPE_DE_PIX})).json()

    assert corpo["explicacao_indisponivel"] is False
    assert corpo["verificacao_externa_indisponivel"] is False


async def test_mensagem_legitima_da_baixo(cliente: AsyncClient) -> None:
    texto = (
        "Sua fatura do cartão final 1234 fecha em 05/09 e vence em 12/09. "
        "Consulte os valores pelo aplicativo ou nas agências."
    )

    corpo = (await cliente.post("/api/analises", json={"texto": texto})).json()

    assert corpo["nivel_risco"] == "BAIXO"
    assert corpo["score"] == 0
    assert corpo["fatores"] == []
    assert corpo["urls_analisadas"] == []


async def test_fator_nao_expoe_trecho_da_mensagem(cliente: AsyncClient) -> None:
    """Invariante 1 no contrato: o que sai da API é o que a LLM vai receber na Fase 7."""
    texto = "URGENTE: faça um PIX para XYZZY4242 e confirme seu CPF."

    corpo = (await cliente.post("/api/analises", json={"texto": texto})).json()

    assert corpo["fatores"]
    assert all("XYZZY4242" not in fator["descricao"] for fator in corpo["fatores"])


# ─── entrada recusada, nunca truncada ─────────────────────────────────────────────────────


async def test_texto_vazio_e_recusado_com_mensagem_em_portugues(cliente: AsyncClient) -> None:
    """Regra de negócio da §2.5: análise sem conteúdo identificável devolve erro informativo."""
    resposta = await cliente.post("/api/analises", json={"texto": "   "})

    assert resposta.status_code == 422
    assert "cole a mensagem" in resposta.json()["detail"].lower()


async def test_texto_so_com_pontuacao_e_recusado(cliente: AsyncClient) -> None:
    resposta = await cliente.post("/api/analises", json={"texto": "... !!! ---"})

    assert resposta.status_code == 422


async def test_texto_acima_do_limite_e_recusado(cliente: AsyncClient) -> None:
    limite = get_settings().texto_max_caracteres

    resposta = await cliente.post("/api/analises", json={"texto": "a" * (limite + 1)})

    assert resposta.status_code == 422
    assert str(limite) in resposta.json()["detail"]


async def test_texto_acima_do_limite_nao_e_truncado_e_analisado(cliente: AsyncClient) -> None:
    """O ponto do teste anterior, dito de outro jeito e pelo motivo que importa.

    Truncar significaria pontuar sobre conteúdo parcial: o pedido de PIX no fim da mensagem
    sumiria e a resposta viria BAIXO. Falso negativo causado por detalhe de implementação é o
    pior tipo — a mensagem longa é recusada, não cortada.
    """
    limite = get_settings().texto_max_caracteres
    texto = "a" * limite + " Faça um PIX de R$ 500 e confirme seu CPF."

    resposta = await cliente.post("/api/analises", json={"texto": texto})

    assert resposta.status_code == 422
    assert "nivel_risco" not in resposta.json()


async def test_texto_no_limite_exato_e_aceito(cliente: AsyncClient) -> None:
    limite = get_settings().texto_max_caracteres

    resposta = await cliente.post("/api/analises", json={"texto": "a" * limite})

    assert resposta.status_code == 200


async def test_campo_texto_ausente_e_recusado(cliente: AsyncClient) -> None:
    resposta = await cliente.post("/api/analises", json={})

    assert resposta.status_code == 422


# ─── orçamento de tempo ───────────────────────────────────────────────────────────────────


async def test_texto_no_tamanho_maximo_analisa_bem_abaixo_do_orcamento(
    cliente: AsyncClient,
) -> None:
    """Guarda de regex catastrófica, não medição de desempenho.

    O orçamento das heurísticas locais é 300ms (ADR-0002). O limite aqui é 1s — margem de 3x,
    larga o bastante para não piscar em CI lento e apertada o bastante para pegar um padrão
    novo com retrocesso exponencial, que é o modo real de estourar isso.
    """
    limite = get_settings().texto_max_caracteres
    texto = ("Confirme seu CPF em www.exemplo-abcdefgh.com para não perder o prazo. " * 200)[
        :limite
    ]

    inicio = perf_counter()
    resposta = await cliente.post("/api/analises", json={"texto": texto})
    duracao = perf_counter() - inicio

    assert resposta.status_code == 200
    assert duracao < 1.0, f"análise levou {duracao:.2f}s"
