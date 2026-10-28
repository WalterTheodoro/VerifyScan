"""POST /api/analises — a fatia vertical da Fase 1: texto entra, nível de risco sai.

Sem OCR, sem API externa e sem login. A IA está desligada aqui (o padrão dos testes): a resposta
é a do motor com o plano B do nível (ADR-0020). A análise com IA está em
`test_api_analise_com_ia.py`.
"""

from time import perf_counter

from httpx import AsyncClient

from app.core.config import get_settings
from app.scoring.regras import carregar_regras

# A mensagem do Gate 1. No texto: urgência (+10), ameaça de bloqueio (+15), solicitação
# financeira (+25) e dados pessoais (+25). No link, desde a Fase 3 (ADR-0022): a marca "bb" fora
# do domínio oficial (+35) e a palavra-isca "regularize" (+15). 125, portanto ALTO.
GOLPE_DE_PIX = (
    "URGENTE: sua conta será bloqueada hoje. Faça um PIX de R$ 49,90 para regularizar "
    "e confirme seu CPF em bb-regularize.xyz"
)


async def test_golpe_de_pix_da_alto_com_os_fatores(cliente: AsyncClient) -> None:
    resposta = await cliente.post("/api/analises", json={"texto": GOLPE_DE_PIX})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["nivel_risco"] == "ALTO"
    assert corpo["score"] == 125
    assert {fator["categoria"] for fator in corpo["fatores"]} == {
        "urgencia",
        "ameaca_bloqueio",
        "solicitacao_financeira",
        "dados_pessoais",
        "link_marca_nao_oficial",
        "link_palavra_isca",
    }


async def test_fator_de_link_vem_com_tipo_dominio(cliente: AsyncClient) -> None:
    corpo = (await cliente.post("/api/analises", json={"texto": GOLPE_DE_PIX})).json()

    tipos = {fator["categoria"]: fator["tipo"] for fator in corpo["fatores"]}
    assert tipos["link_marca_nao_oficial"] == "dominio"
    assert tipos["urgencia"] == "texto"


async def test_link_sozinho_com_marca_fora_do_oficial_da_medio(cliente: AsyncClient) -> None:
    """Sem nenhum sinal de texto, só o link. Antes da Fase 3 isto saía BAIXO com score 0."""
    texto = "Acompanhe em https://correios-entrega.example"

    corpo = (await cliente.post("/api/analises", json={"texto": texto})).json()

    assert corpo["nivel_risco"] == "MEDIO"


async def test_resposta_traz_o_dominio_de_cada_link_e_o_que_se_achou(cliente: AsyncClient) -> None:
    """Fatia 8: a tela mostra o domínio registrável e o que o sistema achou dele, nunca o link
    inteiro. `urls_analisadas` saiu do contrato."""
    corpo = (await cliente.post("/api/analises", json={"texto": GOLPE_DE_PIX})).json()

    assert "urls_analisadas" not in corpo
    assert corpo["links"] == [
        {
            "dominio": "bb-regularize.xyz",
            "observacoes": [
                "usa o nome Banco do Brasil, mas não é um endereço oficial",
                "usa palavras comuns em golpes",
            ],
            "oficial": False,
            "conselho": carregar_regras().dominios.link_conselho,
        }
    ]


async def test_resposta_nunca_traz_o_link_inteiro(cliente: AsyncClient) -> None:
    """Caminho, query e subdomínio são o "atalho pronto" para o golpe: não saem em campo
    nenhum. (A mensagem não volta na resposta da análise; só o histórico a devolve.)"""
    texto = "Pague em https://pagamento.correios-xyzzy.example/taxa-42?cpf=QWERTY"

    resposta = await cliente.post("/api/analises", json={"texto": texto})

    for trecho in ("pagamento.correios", "taxa-42", "QWERTY", "https://"):
        assert trecho not in resposta.text


async def test_sem_ia_a_explicacao_fica_indisponivel(cliente: AsyncClient) -> None:
    """A flag diz à tela que a resposta saiu sem a IA (ADR-0020); a reputação externa ainda não
    existe, e a flag dela segue falsa."""
    corpo = (await cliente.post("/api/analises", json={"texto": GOLPE_DE_PIX})).json()

    assert corpo["explicacao_indisponivel"] is True
    assert corpo["verificacao_externa_indisponivel"] is False


async def test_sem_conta_a_analise_nao_vai_para_o_historico(cliente: AsyncClient) -> None:
    """Campo aditivo do ADR-0015: true só quando a análise foi gravada ligada a uma conta."""
    corpo = (await cliente.post("/api/analises", json={"texto": GOLPE_DE_PIX})).json()

    assert corpo["salva_no_historico"] is False


async def test_mensagem_legitima_da_baixo(cliente: AsyncClient) -> None:
    texto = (
        "Sua fatura do cartão final 1234 fecha em 05/09 e vence em 12/09. "
        "Consulte os valores pelo aplicativo ou nas agências."
    )

    corpo = (await cliente.post("/api/analises", json={"texto": texto})).json()

    assert corpo["nivel_risco"] == "BAIXO"
    assert corpo["score"] == 0
    assert corpo["fatores"] == []
    assert corpo["links"] == []


async def test_fator_nao_expoe_trecho_da_mensagem(cliente: AsyncClient) -> None:
    """A descrição do fator é sempre um template do `regras.yaml`, nunca trecho da mensagem
    (ADR-0004). É também o que a IA recebe como fatores do motor (ADR-0020)."""
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
