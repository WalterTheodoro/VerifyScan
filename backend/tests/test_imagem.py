"""Validação e reencode do print (fatia 9, ADR-0023): tipo pelos bytes, bomba de descompressão,
animação, imagem corrompida, metadados removidos e o tamanho que a Anthropic não reduz."""

import io
import struct
import zlib

import pytest
from PIL import Image, ImageCms

from app.ocr.imagem import (
    LADO_MAX,
    TOKENS_MAX,
    ImagemInvalida,
    formato_pelos_bytes,
    preparar_imagem,
    tamanho_alvo,
    tokens_da_imagem,
)

MAX_BYTES = 5 * 1024 * 1024


def _imagem(formato: str = "PNG", tamanho: tuple[int, int] = (390, 844), **opcoes: object) -> bytes:
    saida = io.BytesIO()
    Image.new("RGB", tamanho, (240, 240, 240)).save(saida, formato, **opcoes)
    return saida.getvalue()


def _chunk_png(tipo: bytes, dados: bytes) -> bytes:
    return (
        struct.pack(">I", len(dados))
        + tipo
        + dados
        + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)
    )


def _segmentos_jpeg(dados: bytes) -> list[tuple[int, bytes]]:
    """Os segmentos do cabeçalho do JPEG, até o início dos dados da imagem (SOS)."""
    assert dados[:2] == b"\xff\xd8"
    segmentos = []
    posicao = 2
    while posicao < len(dados):
        marcador = dados[posicao + 1]
        if marcador == 0xDA:  # SOS: daqui em diante são os pixels
            break
        tamanho = struct.unpack(">H", dados[posicao + 2 : posicao + 4])[0]
        segmentos.append((marcador, dados[posicao + 4 : posicao + 2 + tamanho]))
        posicao += 2 + tamanho
    return segmentos


def _exif_com_gps() -> Image.Exif:
    exif = Image.Exif()
    exif[0x010F] = "Fabricante"  # Make
    exif[0x0112] = 1  # Orientation
    gps = exif.get_ifd(0x8825)
    gps[1] = "S"  # GPSLatitudeRef
    gps[2] = (23.0, 33.0, 0.0)  # GPSLatitude
    gps[3] = "W"
    gps[4] = (46.0, 38.0, 0.0)
    return exif


XMP = (
    b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-'
    b'syntax-ns#"><rdf:Description xmlns:exif="http://ns.adobe.com/exif/1.0/" exif:GPSLatitude='
    b'"23,33.0S"/></rdf:RDF></x:xmpmeta>'
)


def _icc() -> bytes:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


# ── Tipo pelos bytes iniciais ────────────────────────────────────────────────────────────────


def test_formato_pelos_bytes() -> None:
    assert formato_pelos_bytes(_imagem("PNG")) == "PNG"
    assert formato_pelos_bytes(_imagem("JPEG")) == "JPEG"
    assert formato_pelos_bytes(_imagem("WEBP")) == "WEBP"
    assert formato_pelos_bytes(_imagem("GIF")) is None
    assert formato_pelos_bytes(b"%PDF-1.7\n") is None
    assert formato_pelos_bytes(b"isto e texto") is None
    assert formato_pelos_bytes(b"") is None


@pytest.mark.parametrize(
    "dados",
    [
        _imagem("GIF"),
        _imagem("BMP"),
        b"%PDF-1.7\n1 0 obj",
        "Oi, faça um Pix".encode(),
        b"",
    ],
    ids=["gif", "bmp", "pdf", "texto", "vazio"],
)
def test_o_que_nao_e_png_jpeg_nem_webp_e_recusado(dados: bytes) -> None:
    with pytest.raises(ImagemInvalida, match="PNG, JPEG ou WebP"):
        preparar_imagem(dados, MAX_BYTES)


def test_o_tipo_vem_dos_bytes_e_nao_do_que_o_arquivo_diz() -> None:
    """Um GIF com cabeçalho de PNG falsificado não passa: o Pillow só abre o formato detectado."""
    falso = b"\x89PNG\r\n\x1a\n" + _imagem("GIF")
    with pytest.raises(ImagemInvalida):
        preparar_imagem(falso, MAX_BYTES)


def test_acima_do_limite_de_bytes_e_recusado() -> None:
    dados = _imagem("PNG")
    with pytest.raises(ImagemInvalida, match="grande demais"):
        preparar_imagem(dados, max_bytes=len(dados) - 1)


# ── Imagem quebrada, bomba e animação ────────────────────────────────────────────────────────


def test_imagem_truncada_e_recusada() -> None:
    dados = _imagem("PNG", (800, 800))
    with pytest.raises(ImagemInvalida, match="Não conseguimos abrir"):
        preparar_imagem(dados[: len(dados) // 2], MAX_BYTES)


def test_jpeg_corrompido_e_recusado() -> None:
    dados = _imagem("JPEG", (800, 800))
    with pytest.raises(ImagemInvalida, match="Não conseguimos abrir"):
        preparar_imagem(dados[:200], MAX_BYTES)


def test_bomba_de_descompressao_e_recusada_pelo_cabecalho() -> None:
    """Um PNG de poucos bytes que declara 50000 por 50000: recusado antes de descomprimir."""
    cabecalho = struct.pack(">IIBBBBB", 50_000, 50_000, 8, 2, 0, 0, 0)
    bomba = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk_png(b"IHDR", cabecalho)
        + _chunk_png(b"IDAT", zlib.compress(b"\x00" * 64))
        + _chunk_png(b"IEND", b"")
    )
    assert len(bomba) < 200
    with pytest.raises(ImagemInvalida, match="grande demais"):
        preparar_imagem(bomba, MAX_BYTES)


def test_lado_enorme_dentro_do_teto_de_pixels_tambem_e_recusado() -> None:
    cabecalho = struct.pack(">IIBBBBB", 20_000, 100, 8, 2, 0, 0, 0)
    tira = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk_png(b"IHDR", cabecalho)
        + _chunk_png(b"IDAT", zlib.compress(b"\x00" * 64))
        + _chunk_png(b"IEND", b"")
    )
    with pytest.raises(ImagemInvalida, match="grande demais"):
        preparar_imagem(tira, MAX_BYTES)


@pytest.mark.parametrize("formato", ["PNG", "WEBP"])
def test_animacao_e_recusada(formato: str) -> None:
    quadros = [Image.new("RGB", (100, 100), cor) for cor in ("red", "blue")]
    saida = io.BytesIO()
    quadros[0].save(saida, formato, save_all=True, append_images=quadros[1:], duration=100)
    with pytest.raises(ImagemInvalida, match="animação"):
        preparar_imagem(saida.getvalue(), MAX_BYTES)


# ── O que sai: JPEG sem metadados, no tamanho que a API não reduz ────────────────────────────


@pytest.mark.parametrize("formato", ["PNG", "JPEG", "WEBP"])
def test_sai_jpeg_nas_mesmas_dimensoes_quando_ja_cabe(formato: str) -> None:
    preparada = preparar_imagem(_imagem(formato, (1170, 2532)), MAX_BYTES)
    assert formato_pelos_bytes(preparada.jpeg) == "JPEG"
    assert (preparada.largura, preparada.altura) == (1170, 2532)
    assert (preparada.largura_original, preparada.altura_original) == (1170, 2532)
    with Image.open(io.BytesIO(preparada.jpeg)) as aberta:
        assert aberta.size == (1170, 2532)
        assert aberta.mode == "RGB"


def test_imagem_grande_e_reduzida_para_o_limite_da_anthropic() -> None:
    preparada = preparar_imagem(_imagem("PNG", (3840, 2160)), MAX_BYTES)
    assert (preparada.largura, preparada.altura) == (2576, 1449)
    assert tokens_da_imagem(preparada.largura, preparada.altura) <= TOKENS_MAX


def test_jpeg_final_sem_exif_xmp_comentario_nem_icc() -> None:
    """A imagem reduzida herdaria o `info` da original: a saída é montada sem ele."""
    original = io.BytesIO()
    Image.new("RGB", (3000, 4000), (200, 210, 220)).save(
        original,
        "JPEG",
        exif=_exif_com_gps(),
        xmp=XMP,
        comment=b"Foto da casa da Maria",
        icc_profile=_icc(),
    )
    # A fixture traz os quatro, senão o teste não prova nada.
    marcas = [carga[:12] for _, carga in _segmentos_jpeg(original.getvalue())]
    assert any(m.startswith(b"Exif\x00\x00") for m in marcas)
    assert any(m.startswith(b"http://ns.ad") for m in marcas)
    assert any(m.startswith(b"ICC_PROFILE") for m in marcas)
    assert any(marcador == 0xFE for marcador, _ in _segmentos_jpeg(original.getvalue()))

    preparada = preparar_imagem(original.getvalue(), MAX_BYTES)

    segmentos = _segmentos_jpeg(preparada.jpeg)
    for marcador, carga in segmentos:
        assert marcador != 0xFE, "comentário"
        assert marcador != 0xE1, "APP1: EXIF ou XMP"
        assert not (marcador == 0xE2 and carga.startswith(b"ICC_PROFILE")), "perfil ICC"
    with Image.open(io.BytesIO(preparada.jpeg)) as aberta:
        assert not aberta.getexif()
        for chave in ("exif", "xmp", "icc_profile", "comment"):
            assert chave not in aberta.info


@pytest.mark.parametrize("formato", ["PNG", "WEBP"])
def test_metadados_de_png_e_webp_tambem_saem(formato: str) -> None:
    from PIL import PngImagePlugin

    opcoes: dict[str, object] = {"exif": _exif_com_gps(), "icc_profile": _icc()}
    if formato == "PNG":
        texto = PngImagePlugin.PngInfo()
        texto.add_text("Comment", "Foto da casa da Maria")
        texto.add_itxt("XML:com.adobe.xmp", XMP.decode())
        opcoes["pnginfo"] = texto
    else:
        opcoes["xmp"] = XMP
    original = _imagem(formato, (400, 400), **opcoes)
    with Image.open(io.BytesIO(original)) as aberta:
        assert aberta.getexif()

    preparada = preparar_imagem(original, MAX_BYTES)

    assert all(marcador not in (0xE1, 0xFE) for marcador, _ in _segmentos_jpeg(preparada.jpeg))
    with Image.open(io.BytesIO(preparada.jpeg)) as aberta:
        assert not aberta.getexif()
        assert "icc_profile" not in aberta.info


def test_png_transparente_vira_fundo_branco() -> None:
    saida = io.BytesIO()
    Image.new("RGBA", (50, 50), (0, 0, 0, 0)).save(saida, "PNG")
    preparada = preparar_imagem(saida.getvalue(), MAX_BYTES)
    with Image.open(io.BytesIO(preparada.jpeg)) as aberta:
        r, g, b = aberta.convert("RGB").getpixel((25, 25))  # type: ignore[misc]
    assert min(r, g, b) > 245


def test_foto_girada_pelo_exif_e_endireitada() -> None:
    """Orientação 6 (90° horário): a imagem deitada sai em pé, e sem o EXIF."""
    exif = Image.Exif()
    exif[0x0112] = 6
    original = _imagem("JPEG", (400, 200), exif=exif)
    preparada = preparar_imagem(original, MAX_BYTES)
    assert (preparada.largura, preparada.altura) == (200, 400)


# ── tamanho_alvo: o port da função de referência da documentação ────────────────────────────


def test_tamanho_alvo_reproduz_os_exemplos_da_documentacao() -> None:
    # vision-coordinates: o A4 a 130 DPI na camada padrão.
    assert tamanho_alvo(1075, 1520, lado_max=1568, tokens_max=1568) == (924, 1307)
    # vision: tabela de redução.
    assert tamanho_alvo(1920, 1080, lado_max=1568, tokens_max=1568) == (1456, 819)
    # A tabela da página Vision diz 1269 por 952, mas a função de referência da própria documentação
    # dá 1270 por 952: ⌈1270/28⌉·⌈952/28⌉ = 46·34 = 1.564 ≤ 1.568. Seguimos a função (ADR-0023).
    assert tamanho_alvo(2000, 1500, lado_max=1568, tokens_max=1568) == (1270, 952)
    # Alta resolução (Claude 4.7 em diante): os limites usados pela aplicação.
    assert (LADO_MAX, TOKENS_MAX) == (2576, 4784)
    assert tamanho_alvo(1920, 1080) == (1920, 1080)
    assert tamanho_alvo(2000, 1500) == (2000, 1500)
    assert tamanho_alvo(3840, 2160) == (2576, 1449)
    assert tamanho_alvo(1075, 1520) == (1075, 1520)


def test_tamanho_alvo_de_print_de_celular_em_pe() -> None:
    assert tamanho_alvo(1170, 2532) == (1170, 2532)
    largura, altura = tamanho_alvo(1290, 2796)
    assert altura <= LADO_MAX and tokens_da_imagem(largura, altura) <= TOKENS_MAX
    assert abs(largura / altura - 1290 / 2796) < 0.01


def test_tokens_da_imagem() -> None:
    assert tokens_da_imagem(200, 200) == 64
    assert tokens_da_imagem(1000, 1000) == 1296
    assert tokens_da_imagem(1170, 2532) == 42 * 91
