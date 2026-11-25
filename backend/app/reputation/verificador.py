"""URLChecker (§5.4.4 do RFC, ADR-0028): consulta as bases externas, com cache, cota e teto.

Regras que este arquivo garante:

- só o host (Safe Browsing) e o domínio registrável (VirusTotal) saem do processo;
- as duas bases em paralelo, e a etapa inteira dentro de um teto: estourou, a análise segue sem
  reputação, com `indisponivel=True` (RNF09);
- o VirusTotal só é chamado depois de reservar a consulta no contador global (4 por minuto e 500
  por dia, da API pública): sem reserva, não chama;
- resposta do Safe Browsing só é reaproveitada dentro do `cacheDuration` que o Google mandou, e
  nesse prazo o host não é consultado de novo (termos de uso).

Nunca levanta: qualquer falha vira "indisponível".
"""

import asyncio
import hashlib
import logging
from collections.abc import Callable, Coroutine, Iterable, Sequence
from datetime import datetime, timedelta
from typing import Protocol

from app.core.logs import evento
from app.core.metricas import contar_consulta_de_reputacao, contar_falha_de_reputacao
from app.reputation.tipos import (
    Alvo,
    Apontamento,
    FonteIndisponivel,
    ItemDeCache,
    MotivoDaFalha,
    ResultadoReputacao,
    Veredito,
)
from app.schemas.analise import FonteReputacao
from app.services.repositorio_reputacao import RepositorioReputacao

logger = logging.getLogger(__name__)

VALIDADE_DO_VIRUSTOTAL = timedelta(hours=24)


class ConsultaSafeBrowsing(Protocol):
    async def consultar(self, hosts: list[str]) -> dict[str, float]: ...


class ConsultaVirusTotal(Protocol):
    async def consultar(self, dominio: str) -> Veredito: ...


def chave_de_cache(valor: str) -> str:
    """SHA-256 do host ou do domínio: o cache não guarda o que as pessoas consultaram em claro.
    É pseudonimização, não anonimato (errata, item 4): quem tem o domínio refaz o hash."""
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()


class VerificadorDeReputacao:
    def __init__(
        self,
        safe_browsing: ConsultaSafeBrowsing | None,
        virustotal: ConsultaVirusTotal | None,
        repositorio: RepositorioReputacao,
        agora: Callable[[], datetime],
        timeout_s: float,
        virustotal_por_minuto: int,
        virustotal_por_dia: int,
    ) -> None:
        """`None` numa base: sem chave configurada."""
        self._safe_browsing = safe_browsing
        self._virustotal = virustotal
        self._repositorio = repositorio
        self._agora = agora
        self._timeout_s = timeout_s
        self._por_minuto = virustotal_por_minuto
        self._por_dia = virustotal_por_dia

    async def verificar(self, alvos: Sequence[Alvo]) -> ResultadoReputacao:
        if not alvos:
            return ResultadoReputacao()
        # Cada base no próprio teto, as duas ao mesmo tempo: se uma trava, a resposta da outra
        # ainda vale, e a etapa nunca passa de `timeout_s`.
        do_google, do_virustotal = await asyncio.gather(
            self._com_teto("safe_browsing", self._safe_browsing_dos(alvos)),
            self._com_teto("virustotal", self._virustotal_dos(alvos)),
        )
        return ResultadoReputacao(
            apontamentos=do_google.apontamentos + do_virustotal.apontamentos,
            indisponivel=do_google.indisponivel or do_virustotal.indisponivel,
            a_guardar=do_google.a_guardar + do_virustotal.a_guardar,
        )

    async def guardar(self, itens: Sequence[ItemDeCache], timeout_s: float) -> None:
        """Grava o cache, no teto do registro. Falhar aqui só custa uma consulta a mais amanhã."""
        if not itens:
            return
        try:
            async with asyncio.timeout(timeout_s):
                await self._repositorio.guardar(itens, self._agora())
        except Exception as exc:
            logger.warning("Cache de reputação não gravado: %s", type(exc).__name__)

    async def _com_teto(
        self, fonte: FonteReputacao, consulta: Coroutine[object, object, ResultadoReputacao]
    ) -> ResultadoReputacao:
        try:
            async with asyncio.timeout(self._timeout_s):
                return await consulta
        except TimeoutError:
            _falhou(fonte, "timeout")
            return ResultadoReputacao(indisponivel=True)

    # ── Google Safe Browsing ─────────────────────────────────────────────────────────────────

    async def _safe_browsing_dos(self, alvos: Sequence[Alvo]) -> ResultadoReputacao:
        if self._safe_browsing is None:
            return _indisponivel("safe_browsing", "sem_chave")
        dominio_do_host = {alvo.host: alvo.dominio for alvo in alvos}
        hosts = list(dominio_do_host)
        chaves = {chave_de_cache(host): host for host in hosts}
        agora = self._agora()
        # Só correspondência fica no cache, e pelo prazo que o Google deu. Banco fora: sem cache.
        em_cache = await self._ler_cache("safe_browsing", list(chaves), agora)
        apontados = {chaves[chave] for chave in em_cache}
        for _ in apontados:
            contar_consulta_de_reputacao("safe_browsing", "cache")
        a_consultar = [host for host in hosts if host not in apontados]
        a_guardar: list[ItemDeCache] = []
        indisponivel = False
        if a_consultar:
            try:
                novos = await self._safe_browsing.consultar(a_consultar)
            except FonteIndisponivel as falha:
                _falhou("safe_browsing", falha.motivo)
                indisponivel = True
            except Exception:
                _falhou("safe_browsing", "erro")
                indisponivel = True
            else:
                for host in a_consultar:
                    contar_consulta_de_reputacao(
                        "safe_browsing", "malicioso" if host in novos else "limpo"
                    )
                for host, validade_s in novos.items():
                    apontados.add(host)
                    a_guardar.append(
                        ItemDeCache(
                            "safe_browsing",
                            chave_de_cache(host),
                            "malicioso",
                            agora + timedelta(seconds=validade_s),
                        )
                    )
        return ResultadoReputacao(
            apontamentos=_sem_repetir(
                Apontamento(dominio_do_host[host], "safe_browsing", "malicioso")
                for host in hosts
                if host in apontados
            ),
            indisponivel=indisponivel,
            a_guardar=tuple(a_guardar),
        )

    # ── VirusTotal ───────────────────────────────────────────────────────────────────────────

    async def _virustotal_dos(self, alvos: Sequence[Alvo]) -> ResultadoReputacao:
        # `/domains` não recebe endereço numérico: esses ficam só com o Safe Browsing.
        dominios = list(dict.fromkeys(alvo.dominio for alvo in alvos if not alvo.numerico))
        if not dominios:
            return ResultadoReputacao()
        if self._virustotal is None:
            return _indisponivel("virustotal", "sem_chave")
        chaves = {chave_de_cache(dominio): dominio for dominio in dominios}
        agora = self._agora()
        vereditos: dict[str, Veredito] = {
            chaves[chave]: veredito
            for chave, veredito in (
                await self._ler_cache("virustotal", list(chaves), agora)
            ).items()
        }
        for _ in vereditos:
            contar_consulta_de_reputacao("virustotal", "cache")
        a_consultar = [dominio for dominio in dominios if dominio not in vereditos]
        a_guardar: list[ItemDeCache] = []
        indisponivel = False
        if a_consultar and not await self._reservar(len(a_consultar), agora):
            _falhou("virustotal", "cota_local")
            indisponivel = True
            a_consultar = []
        respostas = await asyncio.gather(
            *(self._virustotal.consultar(dominio) for dominio in a_consultar),
            return_exceptions=True,
        )
        for dominio, resposta in zip(a_consultar, respostas, strict=True):
            if isinstance(resposta, FonteIndisponivel):
                _falhou("virustotal", resposta.motivo)
                indisponivel = True
            elif isinstance(resposta, BaseException):
                _falhou("virustotal", "erro")
                indisponivel = True
            else:
                contar_consulta_de_reputacao("virustotal", resposta)
                vereditos[dominio] = resposta
                a_guardar.append(
                    ItemDeCache(
                        "virustotal",
                        chave_de_cache(dominio),
                        resposta,
                        agora + VALIDADE_DO_VIRUSTOTAL,
                    )
                )
        return ResultadoReputacao(
            apontamentos=tuple(
                Apontamento(dominio, "virustotal", vereditos[dominio])
                for dominio in dominios
                if vereditos.get(dominio, "limpo") != "limpo"
            ),
            indisponivel=indisponivel,
            a_guardar=tuple(a_guardar),
        )

    # ── banco ────────────────────────────────────────────────────────────────────────────────

    async def _ler_cache(
        self, fonte: FonteReputacao, chaves: list[str], agora: datetime
    ) -> dict[str, Veredito]:
        """Banco fora ou lento é cache vazio: a consulta acontece mesmo assim."""
        try:
            return await self._repositorio.buscar(fonte, chaves, agora)
        except Exception as exc:
            logger.warning("Cache de reputação não lido: %s", type(exc).__name__)
            return {}

    async def _reservar(self, consultas: int, agora: datetime) -> bool:
        """Sem conseguir contar, não chama: o limite do VirusTotal nunca é arriscado."""
        try:
            return await self._repositorio.reservar(
                "virustotal", agora, consultas, self._por_minuto, self._por_dia
            )
        except Exception as exc:
            logger.warning("Cota do VirusTotal não conferida: %s", type(exc).__name__)
            return False


def _sem_repetir(apontamentos: Iterable[Apontamento]) -> tuple[Apontamento, ...]:
    """Dois hosts do mesmo domínio registrável viram um apontamento só."""
    return tuple(dict.fromkeys(apontamentos))


def _indisponivel(fonte: FonteReputacao, motivo: MotivoDaFalha) -> ResultadoReputacao:
    _falhou(fonte, motivo)
    return ResultadoReputacao(indisponivel=True)


def _falhou(fonte: FonteReputacao, motivo: MotivoDaFalha) -> None:
    """Métrica e evento, só com a base e o motivo: nunca o domínio (ADR-0026)."""
    contar_consulta_de_reputacao(fonte, "indisponivel")
    contar_falha_de_reputacao(fonte, motivo)
    # Chave ausente é configuração, não falha: não enche o log a cada análise com link.
    if motivo != "sem_chave":
        logger.warning(
            "reputacao_indisponivel",
            extra=evento("reputacao_indisponivel", fonte=fonte, motivo=motivo),
        )
