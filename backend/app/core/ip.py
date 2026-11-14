"""O IP de quem pediu, e a chave que o representa sem guardá-lo (fatia 10, ADR-0024).

O navegador fala com o frontend, e o Next repassa /api/* ao backend (ADR-0014): o backend vê o IP
do frontend. Por isso o frontend manda o IP do visitante em `X-VerifyScan-IP`, junto com o segredo
compartilhado em `X-VerifyScan-Segredo`. O backend também é acessível direto, e qualquer um pode
mandar esses cabeçalhos: sem o segredo certo, eles são ignorados.

Fora do proxy, vale a entrada **mais à direita** do `X-Forwarded-For`. O Render não documenta o
cabeçalho; o único registro dele (o quadro de sugestões) diz que ele acrescenta ao que o cliente
mandou, sem limpar. A entrada da esquerda pode ser forjada; a última, quem pôs foi o Render.

O IP puro só existe dentro destas funções: o que sai daqui para o banco e para o limite de login
é o HMAC (`chave_hmac`). Nada aqui loga.
"""

import hashlib
import hmac
import ipaddress

from starlette.datastructures import Headers

CABECALHO_IP = "x-verifyscan-ip"
CABECALHO_SEGREDO = "x-verifyscan-segredo"
IP_DESCONHECIDO = "desconhecido"


def normalizar_ip(texto: str) -> str | None:
    """O IP em forma canônica, ou `None` se o texto não for um IP.

    IPv6 vira a rede /64 dele: quem tem um /64 troca de endereço à vontade, e o limite seria
    contornado trocando o fim. IPv4 escrito como IPv6 (`::ffff:1.2.3.4`) volta a ser IPv4.
    """
    try:
        ip = ipaddress.ip_address(texto.strip())
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return str(ip.ipv4_mapped)
        return str(ipaddress.IPv6Network((ip, 64), strict=False))
    return str(ip)


def ip_do_visitante(cabecalhos: Headers, ip_da_conexao: str | None, segredo_proxy: str) -> str:
    """1. o IP repassado pelo frontend, se o segredo conferir; 2. a última entrada do
    `X-Forwarded-For`; 3. o IP da conexão. Nada válido: `IP_DESCONHECIDO`, uma chave só."""
    segredo_recebido = cabecalhos.get(CABECALHO_SEGREDO)
    # Comparação em tempo constante: uma comparação comum pararia no primeiro caractere
    # diferente, e o tempo da resposta ajudaria a adivinhar o segredo.
    if segredo_recebido is not None and hmac.compare_digest(
        segredo_recebido.encode(), segredo_proxy.encode()
    ):
        repassado = normalizar_ip(cabecalhos.get(CABECALHO_IP, ""))
        if repassado is not None:
            return repassado
    # `getlist`: com dois cabeçalhos de mesmo nome, o primeiro pode ter vindo do cliente.
    encaminhados = cabecalhos.getlist("x-forwarded-for")
    if encaminhados:
        ultimo = normalizar_ip(encaminhados[-1].split(",")[-1])
        if ultimo is not None:
            return ultimo
    return normalizar_ip(ip_da_conexao or "") or IP_DESCONHECIDO


def chave_hmac(segredo: str, valor: str) -> str:
    """HMAC-SHA256 em hex. Sem o segredo, não dá para voltar ao valor nem percorrendo os 2³²
    IPv4; com ele, a mesma entrada dá sempre a mesma chave, que é o que o limite precisa."""
    return hmac.new(segredo.encode(), valor.encode(), hashlib.sha256).hexdigest()
