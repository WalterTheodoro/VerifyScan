// A cota diária de IA vista pela tela (fatia 10, ADR-0024). O backend conta em unidades: texto 1,
// print 3. A frase fala em "análises", como a pessoa pensa, e lembra do print só quando ele já não
// cabe — antes disso, a conta das unidades seria um detalhe a mais para ler.
//
// Sem imports de valor, para o teste rodar no Node direto (type stripping).

/** O print custa 3 unidades: o mesmo número do `UNIDADES_PRINT` do backend. */
const UNIDADES_DO_PRINT = 3;

/** A frase depois de uma análise, ou `null` quando o backend não mandou o número. Zero aqui é a
 *  análise que acabou de usar a última unidade: quando a cota já tinha acabado, quem fala é o
 *  aviso da cota (`aviso_sem_ia`), e esta frase não aparece. */
export function fraseDoRestante(restantes: number | null | undefined): string | null {
  if (restantes === null || restantes === undefined) {
    return null;
  }
  if (restantes <= 0) {
    return "Esta foi a última análise com IA de hoje.";
  }
  const frase =
    restantes === 1
      ? "Resta 1 análise com IA hoje."
      : `Restam ${restantes} análises com IA hoje.`;
  return restantes < UNIDADES_DO_PRINT ? `${frase} Um print conta como 3.` : frase;
}
