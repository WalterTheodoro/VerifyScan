"""Guard de corpus (`tools/guard_corpus.py`) — o script que o CI roda antes de aceitar um caso.

Tudo acontece em `tmp_path`: nada aqui escreve em `corpus/casos/`. O CPF usado é o sintético
de `test_pii.py` (base "123456789", dígitos verificadores calculados), sem dono.
"""

from pathlib import Path

import pytest

from tools.guard_corpus import main

CPF_SINTETICO = "123.456.789-09"


def test_diretorio_limpo_devolve_zero(tmp_path: Path) -> None:
    (tmp_path / "caso.yaml").write_text("mensagem: Seu pacote chegou\n", encoding="utf-8")

    assert main([str(tmp_path)]) == 0


def test_arquivo_com_cpf_devolve_um(tmp_path: Path) -> None:
    (tmp_path / "caso.yaml").write_text(f"mensagem: CPF {CPF_SINTETICO}\n", encoding="utf-8")

    assert main([str(tmp_path)]) == 1


def test_varre_subdiretorios(tmp_path: Path) -> None:
    subdiretorio = tmp_path / "golpes" / "pix"
    subdiretorio.mkdir(parents=True)
    (subdiretorio / "caso.yaml").write_text(f"cpf: {CPF_SINTETICO}\n", encoding="utf-8")

    assert main([str(tmp_path)]) == 1


def test_achado_sai_mascarado_com_linha_e_coluna(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arquivo = tmp_path / "caso.yaml"
    arquivo.write_text(f"id: 1\nmensagem: CPF {CPF_SINTETICO}\n", encoding="utf-8")

    main([str(tmp_path)])

    saida = capsys.readouterr().err
    assert f"{arquivo}:2:15: cpf: ***.***.***-09" in saida
    assert CPF_SINTETICO not in saida
    assert "cpf: 1" in saida  # resumo por tipo


def test_diretorio_inexistente_e_tratado(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    inexistente = tmp_path / "nao-existe"

    codigo = main([str(inexistente)])

    # Não pode dar 0: um caminho errado no workflow deixaria o guard verde para sempre.
    assert codigo == 2
    saida = capsys.readouterr().err
    assert str(inexistente) in saida
    assert "Traceback" not in saida


def test_arquivo_fora_de_utf8_e_tratado(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "caso.yaml").write_bytes("mensagem: não".encode("latin-1"))

    assert main([str(tmp_path)]) == 2
    assert "caso.yaml" in capsys.readouterr().err


def test_arquivo_binario_e_ignorado(tmp_path: Path) -> None:
    (tmp_path / "print.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00" + b"\xff" * 16)

    assert main([str(tmp_path)]) == 0
