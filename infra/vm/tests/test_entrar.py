"""O `entrar.sh` baixa da internet o código que a VM vai rodar como root. Este teste não executa
o script (teste não usa rede): lê o arquivo e confere as opções de cada `curl`."""

import re
from pathlib import Path

ENTRAR = Path(__file__).resolve().parents[1] / "entrar.sh"


def _chamadas_do_curl() -> list[str]:
    # Junta as linhas continuadas com "\" e tira os comentários.
    texto = ENTRAR.read_text(encoding="utf-8").replace("\\\n", " ")
    linhas = [linha for linha in texto.splitlines() if not linha.lstrip().startswith("#")]
    return [linha for linha in linhas if re.search(r"\bcurl\b", linha)]


def test_o_script_baixa_alguma_coisa() -> None:
    """Sem isto, o teste de baixo passaria à toa se o download mudasse de ferramenta."""
    assert _chamadas_do_curl()


def test_todo_download_exige_https_inclusive_nos_redirecionamentos() -> None:
    """O `curl` segue redirecionamentos. Sem estas opções, um deles poderia levar a um endereço
    sem HTTPS, e o que chegasse de lá seria executado na VM."""
    for chamada in _chamadas_do_curl():
        assert "--proto '=https'" in chamada, chamada
        assert "--proto-redir '=https'" in chamada, chamada
        assert chamada.count("https://") == chamada.count("://"), chamada
