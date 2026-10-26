"use client";

import { useEffect } from "react";

import { aquecer } from "../_lib/servidor";

/** Acorda o backend gratuito enquanto a pessoa lê a página: um GET silencioso a /health, uma vez
 *  por carregamento, sem bloquear nem mostrar nada (ADR-0017). Não é keep-alive: só acontece
 *  quando alguém abre o site (ADR-0011). */
export function Aquecimento() {
  useEffect(() => {
    aquecer();
  }, []);
  return null;
}
