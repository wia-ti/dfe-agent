#!/usr/bin/env node
// dfe-agent binario — entry point executado via `npx dfe-agent`.
//
// Em dev (`packages/dfe-agent/`), usa tsx para carregar src/cli.ts direto.
// Em producao (instalado via npm), tsc compila src/cli.ts -> dist/cli.js,
// e este shim apenas re-exporta. O `package.json > bin` aponta para
// dist/bin/dfe-agent.js, mas como src/cli.ts ja tem o guard `if
// (import.meta.url === ...)`, ele se executa quando invocado via tsx.
//
// Em producao, o build copia src/cli.ts para dist/cli.js e empacota.

import("../cli.js")
  .then((m) => m.runCli(process.argv.slice(2)))
  .then((code) => process.exit(code))
  .catch((err) => {
    console.error(`[dfe-agent] erro fatal: ${err.message}`);
    process.exit(1);
  });