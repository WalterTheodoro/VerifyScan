"""Limite de tentativas de senha errada, em memória (fatia 10, ADR-0024; NIST SP 800-63B-4 §3.2.2).

O relógio é injetado: o teste anda no tempo sem esperar.
"""

from app.services.tentativas import LimitadorDeTentativas


class Relogio:
    def __init__(self) -> None:
        self.agora = 1000.0

    def __call__(self) -> float:
        return self.agora


def _limitador(relogio: Relogio, **mudancas: int) -> LimitadorDeTentativas:
    valores = {"max_por_conta": 10, "max_por_ip": 30, "janela_s": 15 * 60, **mudancas}
    return LimitadorDeTentativas(relogio=relogio, **valores)


def test_bloqueia_a_conta_na_decima_falha() -> None:
    relogio = Relogio()
    limitador = _limitador(relogio)

    for tentativa in range(10):
        assert not limitador.bloqueado("maria", f"ip-{tentativa}")
        limitador.registrar_falha("maria", f"ip-{tentativa}")

    assert limitador.bloqueado("maria", "ip-novo")
    assert not limitador.bloqueado("joao", "ip-novo")


def test_bloqueia_o_ip_na_trigesima_falha_em_contas_diferentes() -> None:
    relogio = Relogio()
    limitador = _limitador(relogio)

    for tentativa in range(30):
        limitador.registrar_falha(f"conta-{tentativa}", "ip-1")

    assert limitador.bloqueado("conta-nova", "ip-1")
    assert not limitador.bloqueado("conta-nova", "ip-2")


def test_a_janela_desliza() -> None:
    relogio = Relogio()
    limitador = _limitador(relogio, max_por_conta=2)
    limitador.registrar_falha("maria", "ip")
    relogio.agora += 10 * 60
    limitador.registrar_falha("maria", "ip")
    assert limitador.bloqueado("maria", "ip")

    relogio.agora += 5 * 60  # a primeira falha completa 15 min e sai da janela
    assert not limitador.bloqueado("maria", "ip")

    relogio.agora += 10 * 60  # e a segunda também
    limitador.registrar_falha("maria", "ip")
    assert not limitador.bloqueado("maria", "ip")


def test_acerto_zera_so_a_conta() -> None:
    """NIST SP 800-63B-4 §3.2.2: depois de entrar, as falhas anteriores daquela conta não contam.
    As do IP continuam: elas protegem as outras contas."""
    relogio = Relogio()
    limitador = _limitador(relogio, max_por_conta=2, max_por_ip=3)
    limitador.registrar_falha("maria", "ip")
    limitador.registrar_falha("maria", "ip")

    limitador.limpar_conta("maria")

    assert not limitador.bloqueado("maria", "ip-2")
    limitador.registrar_falha("joao", "ip")
    assert limitador.bloqueado("outra", "ip")


def test_conta_e_ip_com_o_mesmo_texto_nao_se_misturam() -> None:
    relogio = Relogio()
    limitador = _limitador(relogio, max_por_conta=1, max_por_ip=5)

    limitador.registrar_falha("x", "y")

    assert not limitador.bloqueado("y", "x")


def test_sem_ip_conta_so_a_conta() -> None:
    relogio = Relogio()
    limitador = _limitador(relogio, max_por_conta=1)

    limitador.registrar_falha("maria", None)

    assert limitador.bloqueado("maria", None)


def test_mapa_nao_cresce_sem_limite() -> None:
    """Um ataque com e-mails aleatórios não pode encher a memória do processo."""
    relogio = Relogio()
    limitador = LimitadorDeTentativas(
        max_por_conta=10, max_por_ip=400, janela_s=900, relogio=relogio, max_chaves=50
    )

    for tentativa in range(500):
        limitador.registrar_falha(f"conta-{tentativa}", "ip")

    assert limitador.chaves_guardadas <= 50
    # A chave do IP foi a primeira a entrar, mas é atualizada a cada falha: sai por último, e o
    # ataque com e-mails aleatórios não zera o contador do próprio IP.
    assert limitador.bloqueado("conta-nova", "ip")
