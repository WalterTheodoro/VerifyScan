// O print lido na tela (fatia 9, ADR-0023): as frases do contexto e a transcrição do histórico.
//
//   npm test

import assert from "node:assert/strict";
import { test } from "node:test";

import { frasesDoContexto, partesDaTranscricao } from "./print.ts";

test("contexto de golpe vira frases simples", () => {
  assert.deepEqual(
    frasesDoContexto({
      canal: "whatsapp",
      remetente_salvo: "nao",
      aviso_do_app: "sim",
      primeira_mensagem: "sim",
      tem_link_visivel: "sim",
    }),
    [
      "Parece ser uma conversa de WhatsApp.",
      "O número não está salvo nos seus contatos.",
      "O aplicativo mostrou um aviso sobre quem mandou.",
      "Parece ser a primeira mensagem dessa conversa.",
      "Aparece um link no print.",
    ],
  );
});

test("o que não ajuda a conferir não vira frase", () => {
  assert.deepEqual(
    frasesDoContexto({
      canal: "nao_identificado",
      remetente_salvo: "nao_da_para_saber",
      aviso_do_app: "nao",
      primeira_mensagem: "nao_da_para_saber",
      tem_link_visivel: "nao",
    }),
    [],
  );
});

test("no e-mail, quem não está nos contatos não é um número", () => {
  const frases = frasesDoContexto({
    canal: "email",
    remetente_salvo: "nao",
    aviso_do_app: "nao",
    primeira_mensagem: "nao_da_para_saber",
    tem_link_visivel: "nao",
  });
  assert.ok(frases.includes("Quem mandou não está nos seus contatos."));
});

test("a transcrição do histórico volta em partes, com quem mandou", () => {
  const guardada =
    "[enviada pela pessoa]\nOi, quem é?\n\n[recebida]\nMudei de número.\nFaz um Pix?\n\n" +
    "[a pessoa também escreveu]\nRecebi agora";
  assert.deepEqual(partesDaTranscricao(guardada), [
    { de: "pessoa", texto: "Oi, quem é?" },
    { de: "contato", texto: "Mudei de número.\nFaz um Pix?" },
    { de: "escrito", texto: "Recebi agora" },
  ]);
});

test("texto colado, sem marca, volta numa parte só", () => {
  assert.deepEqual(partesDaTranscricao("Pague a taxa."), [{ de: "contato", texto: "Pague a taxa." }]);
});
