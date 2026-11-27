"""O aviso de que o backup ou a restauração falhou (ADR-0029). O backup roda de madrugada, sem
ninguém olhando: sem isto, uma falha ficaria só no log da VM.

O aviso é um evento no Sentry do backend, o mesmo projeto que já manda e-mail quando aparece
um erro. O endereço (o DSN) vem do segredo `SENTRY-DSN` do cofre; sem ele, a falha fica só no
log. Para conferir, a pedido, que o aviso chega:

    python3 -m vm.alerta

O que vai no evento: o que falhou e um motivo curto, escrito por este código. Nunca a saída de
erro do Postgres (pode citar dado), nome de máquina, endereço IP nem string de conexão. De uma
exceção inesperada sai só o tipo, nunca a mensagem (CLAUDE.md §5, invariante 2).

Só biblioteca padrão: o evento é um POST no formato de envelope do Sentry
(https://develop.sentry.dev/sdk/foundations/envelopes/). A rede entra por parâmetro, como no
`azure.py`.
"""

import json
import sys
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import urlsplit

from vm import config
from vm.azure import Azure, Pedir, pedir_http
from vm.sistema import dizer

SEGREDO_DO_DSN = "SENTRY-DSN"
# O mesmo ambiente que o compose.yml dá ao backend: o evento cai nas mesmas regras de aviso.
AMBIENTE = "producao"
_CLIENTE = "verifyscan-vm/1"

# Recebe o motivo, curto e sem dado de ninguém.
Avisar = Callable[[str], None]


class LeitorDeSegredos(Protocol):
    def ler_segredo(self, cofre: str, nome: str) -> str | None: ...


def _endereco(dsn: str) -> tuple[str, str]:
    """Do DSN (`https://CHAVE@HOST/CAMINHO/PROJETO`) saem o endereço do envelope e a chave."""
    partes = urlsplit(dsn)
    prefixo, _, projeto = partes.path.rpartition("/")
    if not (partes.scheme and partes.hostname and partes.username and projeto):
        raise ValueError("DSN fora do formato")
    # O host como veio (com a porta, se houver), sem a chave que fica antes do "@".
    host = partes.netloc.rpartition("@")[2]
    return f"{partes.scheme}://{host}{prefixo}/api/{projeto}/envelope/", partes.username


def _envelope(o_que: str, motivo: str, agora: datetime) -> bytes:
    """Três linhas: o cabeçalho do envelope, o do item e o evento."""
    identificador = uuid.uuid4().hex
    evento = {
        "event_id": identificador,
        "timestamp": agora.isoformat(),
        "platform": "python",
        "level": "error",
        "logger": "verifyscan.vm",
        "environment": AMBIENTE,
        "logentry": {"formatted": f"{o_que}: {motivo}"},
        # Falhas com o mesmo motivo ficam juntas no Sentry, numa ocorrência só.
        "fingerprint": ["verifyscan-vm", o_que, motivo],
        "tags": {"origem": "vm"},
    }
    carga = json.dumps(evento, ensure_ascii=False).encode()
    cabecalho = json.dumps({"event_id": identificador, "sent_at": agora.isoformat()}).encode()
    item = json.dumps({"type": "event", "length": len(carga)}).encode()
    return b"\n".join((cabecalho, item, carga)) + b"\n"


def avisar_falha(
    o_que: str,
    motivo: str,
    *,
    cofre: LeitorDeSegredos,
    pedir: Pedir = pedir_http,
    agora: datetime | None = None,
) -> bool:
    """Manda o evento. Devolve se ele foi aceito. Nunca lança: o aviso não pode derrubar, nem
    esconder, a falha que ele está avisando."""
    try:
        dsn = cofre.ler_segredo(config.COFRE, SEGREDO_DO_DSN)
        if dsn is None or not dsn.strip() or dsn == config.A_PREENCHER:
            dizer(f"AVISO_NAO_ENVIADO: o {SEGREDO_DO_DSN} não está no cofre; fica só neste log.")
            return False
        endereco, chave = _endereco(dsn.strip())
        autenticacao = f"Sentry sentry_version=7, sentry_client={_CLIENTE}, sentry_key={chave}"
        cabecalhos = {
            "Content-Type": "application/x-sentry-envelope",
            "User-Agent": _CLIENTE,
            "X-Sentry-Auth": autenticacao,
        }
        status, _ = pedir("POST", endereco, cabecalhos, _envelope(o_que, motivo, agora or _agora()))
    except Exception as erro:
        # Qualquer erro, de propósito (rede, cofre, DSN errado). Só o tipo vai para o log: a
        # mensagem de um erro de rede traz o endereço, que é o DSN.
        dizer(f"AVISO_NAO_ENVIADO: {type(erro).__name__}.")
        return False
    if status != 200:
        dizer(f"AVISO_NAO_ENVIADO: o Sentry respondeu {status}.")
        return False
    dizer("AVISO_ENVIADO: a falha foi registrada no Sentry.")
    return True


def _agora() -> datetime:
    return datetime.now(UTC)


def com_aviso(
    o_que: str,
    tarefa: Callable[[Avisar], int],
    *,
    cofre: LeitorDeSegredos,
    pedir: Pedir = pedir_http,
) -> int:
    """Roda a tarefa entregando a ela o `avisar`. Se ela quebrar de um jeito que não previu
    (a rede cair no meio, por exemplo), avisa também, e o erro segue como erro."""

    def avisar(motivo: str) -> None:
        avisar_falha(o_que, motivo, cofre=cofre, pedir=pedir)

    try:
        return tarefa(avisar)
    except Exception as erro:
        avisar(f"erro inesperado ({type(erro).__name__})")
        raise


def main() -> int:
    """Um evento de teste, para conferir de ponta a ponta que o e-mail chega."""
    enviado = avisar_falha(
        "Teste do aviso da VM", "pedido à mão; nada falhou", cofre=Azure(), agora=_agora()
    )
    return 0 if enviado else 1


if __name__ == "__main__":
    sys.exit(main())
