// O id da requisição, que o proxy do Next gera e o backend põe em todo log dela (ADR-0026).
//
// Com ele dá para seguir um pedido do navegador até o log do backend: o backend devolve o mesmo
// id no cabeçalho da resposta.

export const CABECALHO_REQUEST_ID = "x-request-id";

/** Os cabeçalhos com um id novo. O que o navegador tiver mandado nesse cabeçalho é trocado: o id
 *  vai parar nos logs, e quem escolhe o valor é o servidor. Altera e devolve o mesmo objeto. */
export function comRequestId(cabecalhos: Headers, id: string = crypto.randomUUID()): Headers {
  cabecalhos.set(CABECALHO_REQUEST_ID, id);
  return cabecalhos;
}
