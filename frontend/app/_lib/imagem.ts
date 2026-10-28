// O print antes de sair do navegador (fatia 9, ADR-0023): reduzir às dimensões que a Anthropic
// processa sem reduzir de novo, e reencodar pelo canvas em JPEG. O canvas desenha só os pixels:
// o arquivo que sai não tem EXIF (que pode trazer o GPS de onde a foto foi tirada) nem XMP. Mesmo
// assim, `temMetadados` confere os bytes antes do envio, e a tela recusa enviar se sobrar algum.
// O backend reencoda de novo com o Pillow: são duas barreiras.
//
// Este arquivo não importa nada: o teste roda no Node direto (type stripping), como o do
// `servidor.ts`. O que depende do navegador (canvas, createImageBitmap) só roda dentro de
// `prepararImagem`, nunca na carga do módulo.

/** Os tipos que o botão aceita. O backend confere de novo pelos bytes iniciais. */
export const TIPOS_ACEITOS = ["image/png", "image/jpeg", "image/webp"];

/** Camada de alta resolução da Anthropic (Claude 4.7 em diante, o que inclui o Haiku 5.5): lado
 *  de até 2.576 px e até 4.784 tokens visuais, um token por bloco de 28 por 28 px. */
export const LADO_MAX = 2576;
export const TOKENS_MAX = 4784;
const LADO_DO_BLOCO = 28;

/** JPEG de qualidade boa: o texto do print precisa continuar nítido depois deste passe e do
 *  passe do backend. */
export const QUALIDADE_JPEG = 0.9;

/** Teto do arquivo escolhido, antes de reduzir: protege a memória do celular. O que sai daqui
 *  fica bem abaixo dos 5 MB do backend. */
export const ARQUIVO_MAX_BYTES = 30 * 1024 * 1024;

export class ImagemRecusada extends Error {}

export function tokensDaImagem(largura: number, altura: number): number {
  return Math.ceil(largura / LADO_DO_BLOCO) * Math.ceil(altura / LADO_DO_BLOCO);
}

/** Arredonda o .5 para o par, como o `round` do Python e a API da Anthropic. */
function arredondarParaOPar(valor: number): number {
  const piso = Math.floor(valor);
  if (valor - piso !== 0.5) {
    return Math.round(valor);
  }
  return piso % 2 === 0 ? piso : piso + 1;
}

/** O maior tamanho, na mesma proporção, que a API processa sem reduzir. Port da função de
 *  referência da documentação (Coordinates and bounding boxes), a mesma de `app/ocr/imagem.py`. */
export function tamanhoAlvo(
  largura: number,
  altura: number,
  ladoMax = LADO_MAX,
  tokensMax = TOKENS_MAX,
): [number, number] {
  const cabe = (w: number, h: number) =>
    Math.ceil(w / LADO_DO_BLOCO) * LADO_DO_BLOCO <= ladoMax &&
    Math.ceil(h / LADO_DO_BLOCO) * LADO_DO_BLOCO <= ladoMax &&
    tokensDaImagem(w, h) <= tokensMax;

  if (cabe(largura, altura)) {
    return [largura, altura];
  }
  if (altura > largura) {
    const [novaAltura, novaLargura] = tamanhoAlvo(altura, largura, ladoMax, tokensMax);
    return [novaLargura, novaAltura];
  }
  const proporcao = largura / altura;
  let cabeSempre = 1;
  let nuncaCabe = largura;
  while (cabeSempre + 1 < nuncaCabe) {
    const meio = Math.floor((cabeSempre + nuncaCabe) / 2);
    if (cabe(meio, Math.max(arredondarParaOPar(meio / proporcao), 1))) {
      cabeSempre = meio;
    } else {
      nuncaCabe = meio;
    }
  }
  return [cabeSempre, Math.max(arredondarParaOPar(cabeSempre / proporcao), 1)];
}

// ── Metadados ────────────────────────────────────────────────────────────────────────────────

const XMP_NO_JPEG = "http://ns.adobe.com/xap/1.0/\0";

function comecaCom(bytes: Uint8Array, inicio: number, texto: string): boolean {
  if (inicio + texto.length > bytes.length) {
    return false;
  }
  for (let i = 0; i < texto.length; i++) {
    if (bytes[inicio + i] !== texto.charCodeAt(i)) {
      return false;
    }
  }
  return true;
}

/** Os metadados que importam para a privacidade — EXIF (onde mora o GPS) e XMP (que também pode
 *  trazer o GPS) — num JPEG, PNG ou WebP. Lê só a estrutura do arquivo, sem decodificar a imagem.
 *  Formato desconhecido conta como "tem": melhor recusar do que enviar sem saber. */
export function temMetadados(bytes: Uint8Array): boolean {
  if (bytes[0] === 0xff && bytes[1] === 0xd8) {
    return jpegTemMetadados(bytes);
  }
  if (comecaCom(bytes, 0, "\x89PNG\r\n\x1a\n")) {
    return pngTemMetadados(bytes);
  }
  if (comecaCom(bytes, 0, "RIFF") && comecaCom(bytes, 8, "WEBP")) {
    return webpTemMetadados(bytes);
  }
  return true;
}

function jpegTemMetadados(bytes: Uint8Array): boolean {
  let posicao = 2;
  while (posicao + 4 <= bytes.length && bytes[posicao] === 0xff) {
    const marcador = bytes[posicao + 1];
    if (marcador === 0xda || marcador === 0xd9) {
      return false; // começo dos pixels (SOS) ou fim: acabou o cabeçalho
    }
    const tamanho = (bytes[posicao + 2] << 8) | bytes[posicao + 3];
    if (
      marcador === 0xe1 &&
      (comecaCom(bytes, posicao + 4, "Exif\0") || comecaCom(bytes, posicao + 4, XMP_NO_JPEG))
    ) {
      return true;
    }
    posicao += 2 + tamanho;
  }
  return false;
}

function pngTemMetadados(bytes: Uint8Array): boolean {
  let posicao = 8;
  while (posicao + 8 <= bytes.length) {
    const tamanho =
      ((bytes[posicao] << 24) >>> 0) +
      (bytes[posicao + 1] << 16) +
      (bytes[posicao + 2] << 8) +
      bytes[posicao + 3];
    const tipo = String.fromCharCode(...bytes.subarray(posicao + 4, posicao + 8));
    if (tipo === "eXIf") {
      return true;
    }
    if (tipo === "iTXt" && comecaCom(bytes, posicao + 8, "XML:com.adobe.xmp")) {
      return true;
    }
    if (tipo === "IEND") {
      return false;
    }
    posicao += 12 + tamanho;
  }
  return false;
}

function webpTemMetadados(bytes: Uint8Array): boolean {
  let posicao = 12;
  while (posicao + 8 <= bytes.length) {
    const tipo = String.fromCharCode(...bytes.subarray(posicao, posicao + 4));
    if (tipo === "EXIF" || tipo === "XMP ") {
      return true;
    }
    const tamanho =
      bytes[posicao + 4] |
      (bytes[posicao + 5] << 8) |
      (bytes[posicao + 6] << 16) |
      ((bytes[posicao + 7] << 24) >>> 0);
    posicao += 8 + tamanho + (tamanho % 2);
  }
  return false;
}

/** Base64 dos bytes, em pedaços: `String.fromCharCode(...bytes)` de uma vez estoura a pilha com
 *  um print de 1 MB. */
export function paraBase64(bytes: Uint8Array): string {
  let binario = "";
  const pedaco = 0x8000;
  for (let i = 0; i < bytes.length; i += pedaco) {
    binario += String.fromCharCode(...bytes.subarray(i, i + pedaco));
  }
  return btoa(binario);
}

// ── No navegador ─────────────────────────────────────────────────────────────────────────────

export type ImagemPreparada = {
  /** O JPEG que vai para o backend, já sem metadados. */
  bytes: Uint8Array;
  /** Endereço local (`blob:`) do mesmo JPEG, para a miniatura: a pessoa vê o que vai sair. */
  miniatura: string;
  nome: string;
  largura: number;
  altura: number;
};

/** Reduz, reencoda e confere. Recusa com uma frase para a pessoa (`ImagemRecusada`). */
export async function prepararImagem(arquivo: File): Promise<ImagemPreparada> {
  if (!TIPOS_ACEITOS.includes(arquivo.type)) {
    throw new ImagemRecusada("Envie o print como imagem PNG, JPEG ou WebP.");
  }
  if (arquivo.size > ARQUIVO_MAX_BYTES) {
    throw new ImagemRecusada("Esta imagem é grande demais. Envie um print da tela, sem ampliar.");
  }
  let bitmap: ImageBitmap;
  try {
    // "from-image": uma foto de câmera girada pelo EXIF chega em pé ao canvas.
    bitmap = await createImageBitmap(arquivo, { imageOrientation: "from-image" });
  } catch {
    throw new ImagemRecusada(
      "Não conseguimos abrir esta imagem. Tire o print de novo, ou copie e cole o texto da " +
        "mensagem.",
    );
  }
  const [largura, altura] = tamanhoAlvo(bitmap.width, bitmap.height);
  const canvas = document.createElement("canvas");
  canvas.width = largura;
  canvas.height = altura;
  const contexto = canvas.getContext("2d");
  if (!contexto) {
    bitmap.close();
    throw new ImagemRecusada("Seu navegador não conseguiu preparar a imagem. Tente outro print.");
  }
  // Fundo branco: o JPEG não tem transparência, e um PNG transparente ficaria preto.
  contexto.fillStyle = "#ffffff";
  contexto.fillRect(0, 0, largura, altura);
  contexto.drawImage(bitmap, 0, 0, largura, altura);
  bitmap.close();
  const blob = await new Promise<Blob | null>((resolver) =>
    canvas.toBlob(resolver, "image/jpeg", QUALIDADE_JPEG),
  );
  if (!blob) {
    throw new ImagemRecusada("Seu navegador não conseguiu preparar a imagem. Tente outro print.");
  }
  const bytes = new Uint8Array(await blob.arrayBuffer());
  if (temMetadados(bytes)) {
    throw new ImagemRecusada(
      "Não conseguimos tirar os dados escondidos desta imagem, então ela não foi enviada. " +
        "Tente outro print.",
    );
  }
  return {
    bytes,
    miniatura: URL.createObjectURL(blob),
    nome: arquivo.name || "print colado",
    largura,
    altura,
  };
}
