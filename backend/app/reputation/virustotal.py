"""VirusTotal, API v3 pública: `GET /domains/{dominio}`. ADR-0028.

Vai só o domínio registrável (`exemplo.com`, sem subdomínio). Atenção, registrada no ADR e no
aviso de privacidade: o VirusTotal avisa que o que é consultado passa a constar na base dele,
visível à comunidade, e pode ser examinado por ele.

A chave vai no cabeçalho `x-apikey`. Como no Safe Browsing, nenhuma exceção carrega a URL.
"""

import httpx

from app.reputation.tipos import FonteIndisponivel, Veredito, para_consulta
from app.scoring.regras import LimiaresVirusTotal

ENDERECO = "https://www.virustotal.com/api/v3/domains/"


class ClienteVirusTotal:
    def __init__(
        self, http: httpx.AsyncClient, chave: str, timeout_s: float, limiares: LimiaresVirusTotal
    ) -> None:
        self._http = http
        self._chave = chave
        self._timeout_s = timeout_s
        self._limiares = limiares

    async def consultar(self, dominio: str) -> Veredito:
        try:
            resposta = await self._http.get(
                ENDERECO + para_consulta(dominio),
                headers={"x-apikey": self._chave},
                timeout=self._timeout_s,
            )
        except httpx.TimeoutException:
            raise FonteIndisponivel("timeout") from None
        except httpx.HTTPError:
            raise FonteIndisponivel("erro") from None
        if resposta.status_code == 404:
            # Domínio que o VirusTotal não conhece: ninguém o apontou.
            return "limpo"
        if resposta.status_code == 429:
            raise FonteIndisponivel("limite")
        if resposta.status_code != 200:
            raise FonteIndisponivel("http")
        try:
            contagem = resposta.json()["data"]["attributes"]["last_analysis_stats"]
            maliciosos, suspeitos = int(contagem["malicious"]), int(contagem["suspicious"])
        except (ValueError, TypeError, KeyError):
            raise FonteIndisponivel("resposta") from None
        return self._classificar(maliciosos, suspeitos)

    def _classificar(self, maliciosos: int, suspeitos: int) -> Veredito:
        limiares = self._limiares
        if maliciosos >= limiares.malicioso_a_partir_de:
            return "malicioso"
        if (
            maliciosos >= limiares.suspeito_com_maliciosos
            or suspeitos >= limiares.suspeito_com_suspeitos
        ):
            return "suspeito"
        return "limpo"
