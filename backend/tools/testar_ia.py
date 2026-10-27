"""Roda as amostras de `tools/amostras_ia.yaml` contra a API real da Anthropic (ADR-0020).

    cd backend
    uv run python -m tools.testar_ia

NÃO roda no CI: chama a rede e custa dinheiro (pouco: centavos de dólar). Lê a chave do `.env` da
raiz, pelo mesmo `Settings` da aplicação, e liga a IA só neste processo — não importa o valor de
`IA_ATIVADA`. A chave nunca é impressa.

Para cada amostra: o nível do motor, o sugerido pela IA, o final (a regra fixa), o tipo que a IA
escreveu, a latência e, quando a IA não entrou, o motivo do plano B. No fim, tokens e custo.

Isto não substitui o corpus da Fase 2: são 13 casos sintéticos, sem rótulo independente.
"""

import asyncio
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import yaml
from anthropic import AsyncAnthropic

from app.api.deps import obter_servico_analise
from app.core.config import get_settings
from app.formulator.analisador import AnalisadorIA
from app.formulator.cliente import ClienteAnthropic, RespostaIA
from app.formulator.prompt import EntradaIA
from app.scoring.combinacao import combinar

AMOSTRAS = Path(__file__).parent / "amostras_ia.yaml"

# Preço de tabela do Haiku 5.5 em US$ por milhão de tokens (prompt até 100 mil tokens), como
# publicado em outubro de 2026. Confira antes de citar: é estimativa, não fatura.
PRECO_ENTRADA = 0.10
PRECO_SAIDA = 0.50


class ClienteQueConta:
    """Repassa ao cliente real e guarda os tokens da última resposta."""

    def __init__(self, cliente: ClienteAnthropic) -> None:
        self._cliente = cliente
        self.ultima: RespostaIA | None = None

    async def gerar(self, sistema: str, entrada: str) -> RespostaIA:
        self.ultima = None
        self.ultima = await self._cliente.gerar(sistema, entrada)
        return self.ultima


class MotivoDoPlanoB(logging.Handler):
    """Lê o tipo da exceção do WARNING do `AnalisadorIA` — o mesmo que vai para o log."""

    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.motivo: str | None = None

    def emit(self, registro: logging.LogRecord) -> None:
        argumentos = registro.args
        self.motivo = str(argumentos[0]) if isinstance(argumentos, tuple) and argumentos else "?"


@dataclass
class Linha:
    id: str
    rotulo: str
    motor: str
    ia: str
    final: str
    latencia_ms: int
    plano_b: str
    tipo: str


async def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    settings = get_settings()
    if settings.anthropic_api_key is None:
        print("Defina ANTHROPIC_API_KEY no .env da raiz do repositório para rodar este script.")
        return 1

    sdk = AsyncAnthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
        timeout=settings.ia_timeout_s,
        max_retries=0,
    )
    cliente = ClienteQueConta(
        ClienteAnthropic(sdk, modelo=settings.ia_modelo, max_tokens=settings.ia_max_tokens)
    )
    analisador = AnalisadorIA(cliente, timeout_s=settings.ia_timeout_s)
    motivo = MotivoDoPlanoB()
    logging.getLogger("app.formulator.analisador").addHandler(motivo)
    servico = obter_servico_analise()

    with AMOSTRAS.open(encoding="utf-8") as arquivo:
        amostras = yaml.safe_load(arquivo)["amostras"]

    print(
        f"Modelo: {settings.ia_modelo} · teto {settings.ia_timeout_s:g} s · "
        f"{len(amostras)} amostras\n"
    )
    linhas: list[Linha] = []
    tokens_entrada = tokens_saida = 0
    try:
        for amostra in amostras:
            resposta = servico.analisar(amostra["texto"])
            motivo.motivo = None
            inicio = time.perf_counter()
            resultado = await analisador.avaliar(
                EntradaIA(
                    mensagem=amostra["texto"],
                    nivel_motor=resposta.nivel_motor,
                    fatores=tuple(resposta.fatores),
                    urls=tuple(resposta.urls_analisadas),
                )
            )
            latencia_ms = round((time.perf_counter() - inicio) * 1000)
            if cliente.ultima is not None:
                tokens_entrada += cliente.ultima.tokens_entrada
                tokens_saida += cliente.ultima.tokens_saida
            nivel_ia = resultado.nivel_sugerido if resultado else None
            linhas.append(
                Linha(
                    id=amostra["id"],
                    rotulo=amostra["rotulo"],
                    motor=resposta.nivel_motor,
                    ia=nivel_ia or "—",
                    final=combinar(resposta.nivel_motor, nivel_ia),
                    latencia_ms=latencia_ms,
                    plano_b="não" if resultado else f"sim ({motivo.motivo})",
                    tipo=resultado.explicacao.tipo if resultado else "—",
                )
            )
            print(f"  {amostra['id']}: {latencia_ms} ms")
    finally:
        await sdk.close()

    _imprimir(linhas)
    custo = (tokens_entrada * PRECO_ENTRADA + tokens_saida * PRECO_SAIDA) / 1_000_000
    latencias = sorted(linha.latencia_ms for linha in linhas)
    print(
        f"\nTokens: {tokens_entrada} de entrada, {tokens_saida} de saída · custo estimado "
        f"US$ {custo:.4f} · latência mediana {latencias[len(latencias) // 2]} ms, "
        f"máxima {latencias[-1]} ms"
    )
    return 0


def _imprimir(linhas: list[Linha]) -> None:
    cabecalho = ("amostra", "rótulo", "motor", "IA", "final", "ms", "plano B", "tipo")
    tabela = [
        (x.id, x.rotulo, x.motor, x.ia, x.final, str(x.latencia_ms), x.plano_b, x.tipo)
        for x in linhas
    ]
    larguras = [
        max(len(str(c)) for c in coluna) for coluna in zip(cabecalho, *tabela, strict=False)
    ]
    print()
    for valores in (cabecalho, *tabela):
        print(
            "  ".join(str(v).ljust(largura) for v, largura in zip(valores, larguras, strict=True))
        )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
