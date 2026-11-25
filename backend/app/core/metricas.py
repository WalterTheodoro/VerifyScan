"""Métricas da aplicação, no formato do Prometheus (ADR-0026). Saem em `GET /metrics`.

Só contagens e durações, com rótulos de conjunto fechado: tipo, nível, motivo, método, template
da rota e status. Nenhum rótulo leva conteúdo, endereço, conta nem caminho cru — um rótulo aberto
seria um vazamento e, de quebra, uma série nova a cada valor.

Um registro próprio, e não o global da biblioteca: aqui só entra o que este módulo declara (o
global traz as métricas do processo e do coletor de lixo do Python).

Limitação (ADR-0026): os contadores vivem na memória do processo. Zeram a cada reinício — no
Render gratuito, a cada sono — e, com mais de um worker, cada um conta o seu.
"""

from typing import Literal

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

TipoDeAnalise = Literal["texto", "print"]
MotivoDaFalha = Literal["timeout", "http", "forma", "outro"]

REGISTRO = CollectorRegistry()

# Até 30 s: o KPI da análise (invariante 8).
_FAIXAS_DA_ANALISE = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 15, 20, 30)

_ANALISES = Counter(
    "verifyscan_analises",
    "Análises concluídas, por tipo e nível final.",
    ["tipo", "nivel_final"],
    registry=REGISTRO,
)
_DURACAO_DA_ANALISE = Histogram(
    "verifyscan_analise_duracao_segundos",
    "Duração da análise inteira, da entrada à resposta.",
    ["tipo"],
    buckets=_FAIXAS_DA_ANALISE,
    registry=REGISTRO,
)
_IA_FALHAS = Counter(
    "verifyscan_ia_falhas",
    "Chamadas à IA que caíram no plano B, por motivo.",
    ["motivo"],
    registry=REGISTRO,
)
_IA_SUBIU_NIVEL = Counter(
    "verifyscan_ia_subiu_nivel",
    "Análises em que o nível final ficou acima do nível do motor.",
    registry=REGISTRO,
)
_COTA_EXCEDIDA = Counter(
    "verifyscan_cota_excedida",
    "Análises que ficaram sem IA pela cota do dia ou pelo teto global de gasto.",
    ["com_conta"],
    registry=REGISTRO,
)
# Reputação de links (ADR-0028). Rótulos de conjunto fechado: a base e o resultado. O domínio
# consultado nunca é rótulo.
_REPUTACAO_CONSULTAS = Counter(
    "verifyscan_reputacao_consultas",
    "Consultas de reputação de domínio, por base e resultado (inclui cache e indisponível).",
    ["fonte", "resultado"],
    registry=REGISTRO,
)
_REPUTACAO_FALHAS = Counter(
    "verifyscan_reputacao_falhas",
    "Vezes em que uma base de reputação não respondeu, por base e motivo.",
    ["fonte", "motivo"],
    registry=REGISTRO,
)
_GASTO_DE_HOJE = Gauge(
    "verifyscan_gasto_ia_dolares_hoje",
    "Gasto com a IA no dia de São Paulo, em dólares, como o banco informou por último.",
    registry=REGISTRO,
)
_REQUISICOES = Counter(
    "http_requisicoes",
    "Requisições atendidas, por método, template da rota e status.",
    ["metodo", "rota", "status"],
    registry=REGISTRO,
)
_DURACAO_HTTP = Histogram(
    "http_duracao_segundos",
    "Duração da requisição, por template da rota.",
    ["rota"],
    buckets=_FAIXAS_DA_ANALISE,
    registry=REGISTRO,
)


def contar_analise(
    tipo: TipoDeAnalise, nivel_final: str, duracao_s: float, *, ia_subiu_nivel: bool
) -> None:
    _ANALISES.labels(tipo=tipo, nivel_final=nivel_final).inc()
    _DURACAO_DA_ANALISE.labels(tipo=tipo).observe(duracao_s)
    if ia_subiu_nivel:
        _IA_SUBIU_NIVEL.inc()


def contar_falha_da_ia(motivo: MotivoDaFalha) -> None:
    _IA_FALHAS.labels(motivo=motivo).inc()


def contar_cota_excedida(*, com_conta: bool) -> None:
    _COTA_EXCEDIDA.labels(com_conta="true" if com_conta else "false").inc()


def contar_consulta_de_reputacao(fonte: str, resultado: str) -> None:
    """`resultado`: limpo, suspeito, malicioso, cache ou indisponivel."""
    _REPUTACAO_CONSULTAS.labels(fonte=fonte, resultado=resultado).inc()


def contar_falha_de_reputacao(fonte: str, motivo: str) -> None:
    _REPUTACAO_FALHAS.labels(fonte=fonte, motivo=motivo).inc()


def anotar_gasto_de_hoje(dolares: float) -> None:
    _GASTO_DE_HOJE.set(dolares)


def contar_requisicao(metodo: str, rota: str, status: int, duracao_s: float) -> None:
    _REQUISICOES.labels(metodo=metodo, rota=rota, status=str(status)).inc()
    _DURACAO_HTTP.labels(rota=rota).observe(duracao_s)


def exposicao() -> bytes:
    """O texto que o Prometheus lê."""
    return generate_latest(REGISTRO)
