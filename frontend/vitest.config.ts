// Testes e cobertura do frontend (ADR-0025). `npm test` roda tudo e gera o relatório em
// `coverage/` (ignorada pelo git); o CI roda o mesmo comando e reprova abaixo do threshold.

import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Só os testes de app/: nunca varre `.next/` nem `node_modules/`.
    include: ["app/**/*.test.{ts,tsx}"],
    // Os testes de lógica rodam em Node, como antes; os de componente e de hook pedem o jsdom
    // na primeira linha do arquivo (`// @vitest-environment jsdom`).
    environment: "node",
    setupFiles: ["./vitest.setup.ts"],
    coverage: {
      provider: "v8",
      // O `include` é o que põe no relatório os arquivos que nenhum teste importa (o antigo
      // `coverage.all`, removido no Vitest 4). Só código: CSS, SVG e o .ico ficam de fora.
      //
      // Todo o código do frontend: `app/` e os três arquivos de código da raiz. Ficam de fora os
      // testes, os de configuração (`*.config.*`, `vitest.setup.ts`) e o `next-env.d.ts`, que o
      // Next gera. A mesma lista vale no SonarQube Cloud (`sonar-project.properties`, ADR-0027).
      include: [
        "app/**/*.{ts,tsx}",
        "proxy.ts",
        "instrumentation.ts",
        "instrumentation-client.ts",
      ],
      exclude: ["app/**/*.test.{ts,tsx}", "**/*.d.ts"],
      // `skipFull: false`: a tabela do terminal lista também os arquivos com 100%, que o Vitest
      // esconde por padrão. É ela que vai na prova de autoria.
      // O `lcov` é o que o SonarQube Cloud lê (ADR-0027). `projectRoot: ".."` escreve os caminhos
      // a partir da raiz do repositório (`frontend/app/...`), que é de onde o Sonar os procura.
      reporter: [
        ["text", { skipFull: false }],
        "html",
        "json-summary",
        ["lcov", { projectRoot: ".." }],
      ],
      reportsDirectory: "coverage",
      // A meta da disciplina. Abaixo dela o `npm test` sai com erro, e o CI reprova.
      thresholds: { lines: 25 },
    },
  },
});
