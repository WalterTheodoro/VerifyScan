// Desmonta o que cada teste de componente renderizou. Sem `globals` no Vitest, a Testing
// Library não registra essa limpeza sozinha, e um teste veria a tela do anterior.

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(cleanup);
