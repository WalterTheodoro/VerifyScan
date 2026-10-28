"""O print que chega: conferir o tipo, recusar o que é perigoso e reencodar em memória (ADR-0023).

Nada aqui toca disco nem rede (invariante 2): entra `bytes`, sai `bytes`. O que sai é um JPEG
novo, montado só com os pixels — sem EXIF (que pode ter o GPS de onde a foto foi tirada), XMP,
comentário nem perfil de cor —, já no tamanho que a Anthropic processa sem reduzir. O frontend
faz o mesmo antes de enviar; aqui é a segunda barreira, para quem chama a API direto.

Puro e síncrono, como os analisadores: o orquestrador roda em `asyncio.to_thread`, porque
decodificar alguns megapixels leva dezenas de milissegundos de CPU.
"""

import io
import logging
import math
from dataclasses import dataclass
from typing import Literal

from PIL import Image, ImageOps

FormatoImagem = Literal["PNG", "JPEG", "WEBP"]

# Camada de alta resolução da Anthropic (Claude 4.7 em diante, o que inclui o Haiku 5.5): lado de
# até 2.576 px e até 4.784 tokens visuais. Acima disso a API reduz a imagem (documentação Vision).
LADO_MAX = 2576
TOKENS_MAX = 4784
LADO_DO_BLOCO = 28

# Teto do que se aceita decodificar. 40 MP cobre a foto de qualquer celular atual; a bomba de
# descompressão (poucos KB que declaram bilhões de pixels) é recusada pelo cabeçalho, antes de
# descomprimir. O `MAX_IMAGE_PIXELS` do Pillow é a segunda barreira — e é global ao processo.
PIXELS_MAX = 40_000_000
LADO_MAX_ENTRADA = 16_384
Image.MAX_IMAGE_PIXELS = PIXELS_MAX

# Um passe de JPEG a mais, quase sem perda: 4:4:4 não borra a cor das letras. A documentação avisa
# que vários passes com perda estragam texto; PNG de 3,7 MP podia passar do limite da API.
QUALIDADE_JPEG = 92

# Em DEBUG, o Pillow descreve cada bloco que lê. Não tem conteúdo, mas não precisa estar no log.
logging.getLogger("PIL").setLevel(logging.INFO)

_FORMATO_ERRADO = "Envie o print como imagem PNG, JPEG ou WebP."
_GRANDE_DEMAIS = "Esta imagem é grande demais. Envie um print da tela, sem ampliar."
_NAO_ABRE = (
    "Não conseguimos abrir esta imagem. Tire o print de novo, ou copie e cole o texto da mensagem."
)
_ANIMACAO = "Envie um print parado, não uma animação."


class ImagemInvalida(Exception):
    """A imagem não pode ser analisada. A mensagem vai para a pessoa: pt-BR e o que fazer."""


@dataclass(frozen=True)
class ImagemPreparada:
    """O JPEG que vai para a leitura, e só números sobre ele — o que pode ir para o log."""

    jpeg: bytes
    largura: int
    altura: int
    largura_original: int
    altura_original: int
    bytes_originais: int


def formato_pelos_bytes(dados: bytes) -> FormatoImagem | None:
    """O tipo pelos bytes iniciais (magic bytes), nunca pela extensão nem pelo Content-Type."""
    if dados.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if dados.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if len(dados) >= 12 and dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "WEBP"
    return None


def tokens_da_imagem(largura: int, altura: int) -> int:
    """Tokens visuais: um por bloco de 28 por 28 px (documentação Vision)."""
    return math.ceil(largura / LADO_DO_BLOCO) * math.ceil(altura / LADO_DO_BLOCO)


def tamanho_alvo(
    largura: int, altura: int, lado_max: int = LADO_MAX, tokens_max: int = TOKENS_MAX
) -> tuple[int, int]:
    """O maior tamanho, na mesma proporção, que a API processa sem reduzir.

    Port da função de referência `resized_size` da documentação (Coordinates and bounding boxes):
    busca binária no lado maior. O `round` do Python arredonda o .5 para o par, como a API.
    """

    def cabe(w: int, h: int) -> bool:
        return (
            math.ceil(w / LADO_DO_BLOCO) * LADO_DO_BLOCO <= lado_max
            and math.ceil(h / LADO_DO_BLOCO) * LADO_DO_BLOCO <= lado_max
            and tokens_da_imagem(w, h) <= tokens_max
        )

    if cabe(largura, altura):
        return (largura, altura)
    if altura > largura:
        nova_altura, nova_largura = tamanho_alvo(altura, largura, lado_max, tokens_max)
        return (nova_largura, nova_altura)
    proporcao = largura / altura
    cabe_sempre, nunca_cabe = 1, largura
    while cabe_sempre + 1 < nunca_cabe:
        meio = (cabe_sempre + nunca_cabe) // 2
        if cabe(meio, max(round(meio / proporcao), 1)):
            cabe_sempre = meio
        else:
            nunca_cabe = meio
    return (cabe_sempre, max(round(cabe_sempre / proporcao), 1))


def preparar_imagem(dados: bytes, max_bytes: int) -> ImagemPreparada:
    """Confere e reencoda. Qualquer recusa é `ImagemInvalida`, com a frase para a pessoa."""
    if len(dados) > max_bytes:
        raise ImagemInvalida(_GRANDE_DEMAIS)
    formato = formato_pelos_bytes(dados)
    if formato is None:
        raise ImagemInvalida(_FORMATO_ERRADO)
    try:
        # `formats`: o Pillow só tenta o formato que os bytes disseram. Abrir lê só o cabeçalho.
        with Image.open(io.BytesIO(dados), formats=[formato]) as aberta:
            largura, altura = aberta.size
            if (
                largura * altura > PIXELS_MAX
                or max(largura, altura) > LADO_MAX_ENTRADA
                or min(largura, altura) < 1
            ):
                raise ImagemInvalida(_GRANDE_DEMAIS)
            if getattr(aberta, "is_animated", False) or getattr(aberta, "n_frames", 1) > 1:
                raise ImagemInvalida(_ANIMACAO)
            aberta.load()
            endireitada = ImageOps.exif_transpose(aberta)
    except ImagemInvalida:
        raise
    except Image.DecompressionBombError as exc:
        raise ImagemInvalida(_GRANDE_DEMAIS) from exc
    except (OSError, ValueError, SyntaxError) as exc:
        # OSError inclui o `UnidentifiedImageError`; SyntaxError é como alguns plugins do Pillow
        # avisam de cabeçalho inválido.
        raise ImagemInvalida(_NAO_ABRE) from exc
    return _reencodar(endireitada, largura, altura, len(dados))


def _reencodar(
    imagem: Image.Image, largura_original: int, altura_original: int, bytes_originais: int
) -> ImagemPreparada:
    """Uma imagem NOVA, só com os pixels: a reduzida herdaria o `info` da original (EXIF, XMP,
    comentário, ICC), e alguns formatos do Pillow gravam esse `info` ao salvar."""
    com_alfa = imagem.convert("RGBA")
    pixels = Image.new("RGB", com_alfa.size, "white")
    pixels.paste(com_alfa, mask=com_alfa.getchannel("A"))
    alvo = tamanho_alvo(*pixels.size)
    if alvo != pixels.size:
        pixels = pixels.resize(alvo, Image.Resampling.LANCZOS)
    saida = Image.new("RGB", alvo)
    saida.paste(pixels)
    assert not saida.info, "a imagem de saída nasce sem metadados"
    jpeg = io.BytesIO()
    saida.save(jpeg, "JPEG", quality=QUALIDADE_JPEG, subsampling=0, optimize=True)
    return ImagemPreparada(
        jpeg=jpeg.getvalue(),
        largura=alvo[0],
        altura=alvo[1],
        largura_original=largura_original,
        altura_original=altura_original,
        bytes_originais=bytes_originais,
    )
