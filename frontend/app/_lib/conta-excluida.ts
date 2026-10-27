// O aviso "Sua conta foi excluída." que a home mostra depois da exclusão (ADR-0019).
//
// Vai por sessionStorage, e nunca pela URL: um link com `?conta=excluida` poderia ser montado por
// qualquer um e mostraria a frase a quem está logado — num site sobre golpes, isso assusta. O
// sessionStorage é da própria aba e só esta aplicação escreve nele. Sem storage (navegação
// privada restrita, cota cheia), o aviso simplesmente não aparece: a pessoa já viu a home
// deslogada.

const CHAVE = "vs_conta_excluida";

/** Chamado logo antes de ir para a home, depois do 204 da exclusão. */
export function marcarContaExcluida(): void {
  try {
    window.sessionStorage.setItem(CHAVE, "1");
  } catch {
    // Sem storage, sem aviso.
  }
}

/** Lê e apaga na mesma hora: o aviso aparece uma vez só, e recarregar a página não o repete. */
export function consumirContaExcluida(): boolean {
  let marcada = false;
  try {
    marcada = window.sessionStorage.getItem(CHAVE) !== null;
  } catch {
    return false;
  }
  try {
    window.sessionStorage.removeItem(CHAVE);
  } catch {
    // Não deu para apagar: o aviso sai mesmo assim, e no pior caso reaparece nesta aba.
  }
  return marcada;
}
