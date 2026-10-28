// Testes do preparo do print (fatia 9, ADR-0023), no `node:test` do próprio Node, sem dependência
// nova. O Node não tem canvas: o verificador de metadados roda sobre arquivos montados aqui, byte a
// byte, e o `prepararImagem` roda com um canvas falso — o que prova a guarda (sobrou metadado, não
// envia). A prova com o canvas de verdade é a medição de tela, que confere os bytes que saem do
// navegador.
//
//   npm test

import assert from "node:assert/strict";
import { afterEach, describe, test } from "node:test";

import {
  ARQUIVO_MAX_BYTES,
  ImagemRecusada,
  LADO_MIN,
  LADO_MAX,
  TOKENS_MAX,
  paraBase64,
  prepararImagem,
  tamanhoAlvo,
  temMetadados,
  tokensDaImagem,
} from "./imagem.ts";

const texto = (s: string) => Array.from(s, (c) => c.charCodeAt(0));

/** Um segmento de JPEG: FF, marcador, tamanho (2 bytes, conta ele mesmo) e a carga. */
function segmento(marcador: number, carga: number[]): number[] {
  const tamanho = carga.length + 2;
  return [0xff, marcador, tamanho >> 8, tamanho & 0xff, ...carga];
}

function jpeg(...segmentos: number[][]): Uint8Array<ArrayBuffer> {
  const jfif = segmento(0xe0, texto("JFIF\0\x01\x01\0\0\x01\0\x01\0\0"));
  // SOS e alguns bytes de "pixels" depois: o verificador para no SOS.
  const sos = [...segmento(0xda, [1, 1, 0, 0, 0x3f, 0]), 0x12, 0x34, 0xff, 0xd9];
  return new Uint8Array([0xff, 0xd8, ...jfif, ...segmentos.flat(), ...sos]);
}

const EXIF_COM_GPS = segmento(0xe1, [
  ...texto("Exif\0\0"),
  ...texto("MM\0*\0\0\0\x08"),
  ...texto("GPSLatitude 23 33 S"),
]);
const XMP = segmento(0xe1, [
  ...texto("http://ns.adobe.com/xap/1.0/\0"),
  ...texto('<x:xmpmeta><rdf:Description exif:GPSLatitude="23,33S"/></x:xmpmeta>'),
]);

function chunkPng(tipo: string, dados: number[]): number[] {
  const n = dados.length;
  return [n >>> 24, (n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff, ...texto(tipo), ...dados, 0, 0, 0, 0];
}

function png(...chunks: number[][]): Uint8Array {
  const ihdr = chunkPng("IHDR", [0, 0, 0, 1, 0, 0, 0, 1, 8, 2, 0, 0, 0]);
  return new Uint8Array([
    ...texto("\x89PNG\r\n\x1a\n"),
    ...ihdr,
    ...chunks.flat(),
    ...chunkPng("IDAT", [1, 2, 3]),
    ...chunkPng("IEND", []),
  ]);
}

function chunkWebp(tipo: string, dados: number[]): number[] {
  const n = dados.length;
  const enchimento = n % 2 ? [0] : [];
  return [...texto(tipo), n & 0xff, (n >> 8) & 0xff, (n >> 16) & 0xff, n >>> 24, ...dados, ...enchimento];
}

function webp(...chunks: number[][]): Uint8Array {
  const corpo = [...texto("WEBP"), ...chunkWebp("VP8 ", [1, 2, 3, 4]), ...chunks.flat()];
  const n = corpo.length;
  return new Uint8Array([...texto("RIFF"), n & 0xff, (n >> 8) & 0xff, (n >> 16) & 0xff, n >>> 24, ...corpo]);
}

describe("temMetadados", () => {
  test("JPEG limpo não tem", () => {
    assert.equal(temMetadados(jpeg()), false);
  });

  test("JPEG com EXIF (e o GPS dentro) tem", () => {
    assert.equal(temMetadados(jpeg(EXIF_COM_GPS)), true);
  });

  test("JPEG com XMP tem: o XMP também pode trazer o GPS", () => {
    assert.equal(temMetadados(jpeg(XMP)), true);
  });

  test("JPEG com outro APP1 que não é EXIF nem XMP não conta", () => {
    assert.equal(temMetadados(jpeg(segmento(0xe1, texto("outra coisa")))), false);
  });

  test("PNG limpo, com eXIf e com XMP", () => {
    assert.equal(temMetadados(png()), false);
    assert.equal(temMetadados(png(chunkPng("eXIf", texto("MM\0*")))), true);
    assert.equal(temMetadados(png(chunkPng("iTXt", texto("XML:com.adobe.xmp\0\0\0\0\0<x/>")))), true);
  });

  test("WebP limpo, com EXIF e com XMP", () => {
    assert.equal(temMetadados(webp()), false);
    assert.equal(temMetadados(webp(chunkWebp("EXIF", texto("MM\0*")))), true);
    assert.equal(temMetadados(webp(chunkWebp("XMP ", texto("<x/>")))), true);
  });

  test("formato desconhecido conta como tem: na dúvida, não envia", () => {
    assert.equal(temMetadados(new Uint8Array(texto("GIF89a"))), true);
  });
});

describe("tamanhoAlvo (port da função de referência da Anthropic)", () => {
  test("exemplos da documentação", () => {
    assert.deepEqual(tamanhoAlvo(1075, 1520, 1568, 1568), [924, 1307]);
    assert.deepEqual(tamanhoAlvo(1920, 1080, 1568, 1568), [1456, 819]);
    // A tabela da página Vision diz 1269; a função de referência dá 1270 (ADR-0023).
    assert.deepEqual(tamanhoAlvo(2000, 1500, 1568, 1568), [1270, 952]);
    assert.deepEqual(tamanhoAlvo(3840, 2160), [2576, 1449]);
  });

  test("igual ao backend num print de celular, que já cabe", () => {
    assert.deepEqual(tamanhoAlvo(1170, 2532), [1170, 2532]);
    const [largura, altura] = tamanhoAlvo(1290, 2796);
    assert.ok(altura <= LADO_MAX && tokensDaImagem(largura, altura) <= TOKENS_MAX);
  });
});

test("paraBase64 aguenta um arquivo grande e bate com o Buffer do Node", () => {
  const bytes = new Uint8Array(200_000).map((_, i) => (i * 31) % 256);
  assert.equal(paraBase64(bytes), Buffer.from(bytes).toString("base64"));
});

// ── prepararImagem com um navegador de mentira ──────────────────────────────────────────────

const globais = globalThis as Record<string, unknown>;
const originais = { ...globais };

afterEach(() => {
  for (const chave of ["createImageBitmap", "document", "URL"]) {
    globais[chave] = originais[chave];
  }
});

function fingirNavegador(
  saidaDoCanvas: Uint8Array<ArrayBuffer>,
  desenhos: number[][],
  [largura, altura] = [3000, 4000],
) {
  globais.createImageBitmap = async () => ({ width: largura, height: altura, close() {} });
  globais.document = {
    createElement: () => ({
      width: 0,
      height: 0,
      getContext: () => ({
        fillStyle: "",
        fillRect() {},
        drawImage: (_: unknown, x: number, y: number, w: number, h: number) =>
          desenhos.push([x, y, w, h]),
      }),
      toBlob: (pronto: (blob: Blob) => void) => pronto(new Blob([saidaDoCanvas])),
    }),
  };
  globais.URL = { createObjectURL: () => "blob:miniatura" };
}

const arquivo = (tipo = "image/jpeg") => new File([new Uint8Array([1, 2, 3])], "print.jpg", { type: tipo });

test("prepararImagem reduz ao tamanho da Anthropic e devolve o JPEG sem metadados", async () => {
  const desenhos: number[][] = [];
  fingirNavegador(jpeg(), desenhos);

  const preparada = await prepararImagem(arquivo());

  assert.equal(temMetadados(preparada.bytes), false);
  assert.deepEqual([preparada.largura, preparada.altura], tamanhoAlvo(3000, 4000));
  assert.deepEqual(desenhos, [[0, 0, preparada.largura, preparada.altura]]);
  assert.equal(preparada.miniatura, "blob:miniatura");
});

test("prepararImagem recusa enviar se o canvas devolver EXIF", async () => {
  fingirNavegador(jpeg(EXIF_COM_GPS), []);
  await assert.rejects(prepararImagem(arquivo()), ImagemRecusada);
});

test("prepararImagem recusa o que não é PNG, JPEG nem WebP", async () => {
  await assert.rejects(prepararImagem(arquivo("image/gif")), /PNG, JPEG ou WebP/);
  await assert.rejects(prepararImagem(arquivo("application/pdf")), ImagemRecusada);
});

// ── Recusas antes de enviar (correção 9.1) ─────────────────────────────────────────────────

test("o limite do arquivo é o do backend: 5 MB (IMAGEM_MAX_BYTES em app/core/config.py)", () => {
  assert.equal(ARQUIVO_MAX_BYTES, 5 * 1024 * 1024);
});

test("arquivo acima do limite é recusado antes de abrir, com o limite na frase", async () => {
  const grande = new File([new Uint8Array(ARQUIVO_MAX_BYTES + 1)], "ruido.png", {
    type: "image/png",
  });
  await assert.rejects(prepararImagem(grande), {
    message: "Este arquivo é grande demais. Envie um print de até 5 MB.",
  });
});

test("o JPEG preparado acima do limite também não sai", async () => {
  const enorme = new Uint8Array(ARQUIVO_MAX_BYTES + 1);
  enorme.set(jpeg());
  fingirNavegador(enorme, []);
  await assert.rejects(prepararImagem(arquivo()), {
    message: "Este arquivo é grande demais. Envie um print de até 5 MB.",
  });
});

test("imagem com o lado menor abaixo de 200 px é recusada, nos dois sentidos", async () => {
  assert.equal(LADO_MIN, 200);
  const tamanhos: [number, number][] = [
    [1170, 199],
    [199, 2532],
  ];
  for (const tamanho of tamanhos) {
    const desenhos: number[][] = [];
    fingirNavegador(jpeg(), desenhos, tamanho);
    await assert.rejects(prepararImagem(arquivo()), {
      message: "Esta imagem é pequena demais para ler. Envie o print inteiro da conversa.",
    });
    assert.deepEqual(desenhos, [], "recusada antes de desenhar");
  }
});

test("200 px no lado menor ainda entra", async () => {
  fingirNavegador(jpeg(), [], [200, 400]);
  const preparada = await prepararImagem(arquivo());
  assert.deepEqual([preparada.largura, preparada.altura], [200, 400]);
});
