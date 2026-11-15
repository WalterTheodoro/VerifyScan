"""Limite de tentativas de senha errada (fatia 10, ADR-0024; NIST SP 800-63B-4 §3.2.2).

Conta as falhas numa janela deslizante, por conta e por IP. O limite é conferido ANTES do banco e
do Argon2: quem passou dele nem chega a gastar os ~19 MiB de uma verificação.

Fica em memória, e não no Postgres como a cota da IA, porque a janela (até 15 min) não passa do
tempo que o Render gratuito leva para dormir parado. Um reinício por ociosidade só apaga falhas que
já tinham saído da janela; quem ataca mantém o processo acordado. Um deploy zera tudo: limitação
aceita e registrada no ADR.

As chaves chegam prontas, já em HMAC (o e-mail e o IP nunca entram aqui em claro). A da conta vale
também para e-mail que não tem conta: o 429 sai igual, e não revela quem está cadastrado.
"""

import time
from collections import deque
from collections.abc import Callable


class LimitadorDeTentativas:
    def __init__(
        self,
        *,
        max_por_conta: int,
        max_por_ip: int,
        janela_s: float,
        relogio: Callable[[], float] = time.monotonic,
        max_chaves: int = 10_000,
    ) -> None:
        """`relogio` monotônico: acertar o relógio do servidor não abre nem fecha a janela.
        `max_chaves` limita a memória contra um ataque com e-mails sempre novos."""
        self._max_por_conta = max_por_conta
        self._max_por_ip = max_por_ip
        self._janela_s = janela_s
        self._relogio = relogio
        self._max_chaves = max_chaves
        self._falhas: dict[str, deque[float]] = {}

    @property
    def chaves_guardadas(self) -> int:
        return len(self._falhas)

    def bloqueado(self, conta: str | None, ip: str | None) -> bool:
        return (conta is not None and self._recentes(f"conta:{conta}") >= self._max_por_conta) or (
            ip is not None and self._recentes(f"ip:{ip}") >= self._max_por_ip
        )

    def registrar_falha(self, conta: str | None, ip: str | None) -> None:
        agora = self._relogio()
        for chave in (f"conta:{conta}" if conta else None, f"ip:{ip}" if ip else None):
            if chave is None:
                continue
            # Tirar e pôr de volta leva a chave para o fim do dicionário, que guarda a ordem de
            # inserção: o começo fica com as chaves que falharam há mais tempo, as primeiras a sair.
            falhas = self._falhas.pop(chave, deque())
            falhas.append(agora)
            self._falhas[chave] = falhas
        if len(self._falhas) > self._max_chaves:
            self._enxugar()

    def limpar_conta(self, conta: str) -> None:
        """Acerto zera a conta, como a NIST recomenda; o IP continua, porque protege as outras."""
        self._falhas.pop(f"conta:{conta}", None)

    def _recentes(self, chave: str) -> int:
        falhas = self._falhas.get(chave)
        if falhas is None:
            return 0
        limite = self._relogio() - self._janela_s
        while falhas and falhas[0] <= limite:
            falhas.popleft()
        if not falhas:
            del self._falhas[chave]
            return 0
        return len(falhas)

    def _enxugar(self) -> None:
        """Primeiro o que venceu; se ainda passar do teto, as chaves sem falha há mais tempo."""
        for chave in list(self._falhas):
            self._recentes(chave)
        while len(self._falhas) > self._max_chaves:
            del self._falhas[next(iter(self._falhas))]
