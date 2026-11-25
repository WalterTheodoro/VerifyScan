"""Do que as bases apontaram para o que o motor soma e a tela mostra (ADR-0028). Puro, sem I/O."""

from collections.abc import Sequence

from app.reputation.tipos import Apontamento
from app.schemas.analise import CategoriaFator, Fator, FonteReputacao
from app.scoring.regras import ConfiguracaoReputacao


def categoria_de(apontamento: Apontamento) -> CategoriaFator:
    if apontamento.fonte == "safe_browsing":
        return "reputacao_safe_browsing"
    if apontamento.veredito == "malicioso":
        return "reputacao_virustotal_malicioso"
    return "reputacao_virustotal_suspeito"


def fatores_de_reputacao(
    config: ConfiguracaoReputacao, apontamentos: Sequence[Apontamento]
) -> list[Fator]:
    """No máximo um fator do Google e um do VirusTotal. Do VirusTotal sai só o mais forte: um
    domínio "malicioso" e outro "suspeito" não somam os dois pesos."""
    categorias = {categoria_de(apontamento) for apontamento in apontamentos}
    if "reputacao_virustotal_malicioso" in categorias:
        categorias.discard("reputacao_virustotal_suspeito")
    fatores = []
    # A ordem do `regras.yaml`, e não a de chegada: a resposta não muda com a ordem das consultas.
    for sinal in config.sinais:
        if sinal.id in categorias:
            fatores.append(
                Fator(
                    tipo="reputacao",
                    categoria=sinal.id,
                    descricao=sinal.descricao.renderizar(),
                    peso=sinal.peso,
                )
            )
    return fatores


def frases_do_dominio(
    config: ConfiguracaoReputacao, apontamentos: Sequence[Apontamento], dominio: str
) -> list[str]:
    """As frases do bloco de links para um domínio, sem repetir."""
    frases: list[str] = []
    for apontamento in apontamentos:
        if apontamento.dominio == dominio:
            frase = config.sinal(categoria_de(apontamento)).no_link.renderizar()
            if frase not in frases:
                frases.append(frase)
    return frases


def fontes_do_dominio(apontamentos: Sequence[Apontamento], dominio: str) -> list[FonteReputacao]:
    return list(dict.fromkeys(a.fonte for a in apontamentos if a.dominio == dominio))
