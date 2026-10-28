"""Contrato de `POST /api/analises` e o vocabulário compartilhado da análise.

`NivelRisco`, `TipoFator`, `CategoriaFator` e `Fator` vivem aqui, e não em cada módulo, porque
são o contrato: é o que a API devolve, o que o `ScoringEngine` agrega e o que, na Fase 8, vira
`IndicadorRisco` no banco. Ter um vocabulário só evita um tipo de domínio e um espelho dele.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

NivelRisco = Literal["BAIXO", "MEDIO", "ALTO"]
"""Sem acento no fio: o valor atravessa JSON, banco e enum. A tela é que escreve 'MÉDIO'."""

TipoFator = Literal["texto", "dominio", "reputacao"]
"""De onde o fator veio. Diverge da §5.5 do RFC de propósito — ver errata, item 8.

O RFC fixa (url/texto/dominio/ocr/email). `url` é grosseiro: na arquitetura real ele se divide
em `dominio` (Fase 3) e `reputacao` (Fase 4), que têm origem e peso distintos. `ocr` não é tipo
de indicador — texto extraído de imagem produz fator de texto, e quem registra a origem é
`Analise.tipo_input`. `email` sai com o EmailAnalyzer, cortado do escopo.
"""

TipoInput = Literal["texto", "imagem"]
"""Como a mensagem chegou: é a procedência que a errata (item 8) tirou de `TipoFator`.

`imagem` é o print da conversa (fatia 9, ADR-0023, migração 0006): a transcrição produz fatores
de texto e de domínio como qualquer mensagem; quem diz que veio de um print é este campo.
"""

CategoriaFator = Literal[
    "urgencia",
    "personificacao_marca",
    "ameaca_bloqueio",
    "premio_falso",
    "solicitacao_financeira",
    "dados_pessoais",
    "instrucao_ao_analisador",
    "link_encurtado",
    "link_ip",
    "link_caracteres_enganosos",
    "link_marca_nao_oficial",
    "link_parecido_com_oficial",
    "link_tld_abusado",
    "link_palavra_isca",
    "link_sem_https",
    "link_truque_endereco",
]
"""Unidade de agregação: cada categoria pontua no máximo uma vez (ADR-0004).

As seis primeiras são as da §5.4.1 do RFC. `instrucao_ao_analisador` não está no RFC: é a defesa
em profundidade contra injeção de prompt, para quando a IA cai (ADR-0020). As `link_*` são os
sinais léxicos do DomainAnalyzer (Fase 3, ADR-0022), com `tipo="dominio"`. As de reputação
entram na Fase 4.
"""


class Fator(BaseModel):
    """Um motivo pelo qual a mensagem pontuou.

    `descricao` é sempre um template do `regras.yaml` já renderizado — nunca texto livre e
    nunca um trecho da mensagem do usuário (invariante 1 / ADR-0004).
    """

    tipo: TipoFator
    categoria: CategoriaFator
    descricao: str
    peso: int = Field(gt=0, description="Pontos que este fator soma ao score.")


class LinkDaMensagem(BaseModel):
    """Um link da mensagem, como a tela o mostra: só o domínio registrável e o que o sistema achou
    dele (fatia 8, ADR-0022). Nunca o link inteiro: caminho e query são o atalho pronto para o
    golpe, exatamente o que a limpeza tira do texto da IA.

    `observacoes` são templates do `regras.yaml`, como a descrição do fator. O domínio vem da
    mensagem e não é gravado: o histórico o recalcula do texto, que só existe com dono.
    """

    dominio: str = Field(description="Domínio registrável (eTLD+1), como texto, nunca link.")
    observacoes: list[str] = Field(min_length=1)
    # Fatia 9 (item 12): o fecho do bloco não pode tratar o endereço oficial como o do golpe.
    oficial: bool = Field(default=False, description="O domínio é o oficial de uma marca.")
    conselho: str = Field(
        description=(
            "A frase do fim do bloco de links, do `regras.yaml`. A tela mostra a de um link não "
            "oficial quando houver; só com todos oficiais, a do oficial."
        )
    )


class Orientacao(BaseModel):
    """A resposta fixa de um nível, lida do `scoring/respostas.yaml` (ADR-0020).

    É o plano B inteiro quando a IA não entra, e o título (e o texto do BAIXO) quando ela entra.
    """

    model_config = ConfigDict(frozen=True)

    titulo: str = Field(min_length=1)
    texto: str | None = None
    passos: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _texto_ou_passos(self) -> Self:
        if not self.texto and not self.passos:
            raise ValueError("cada nível precisa de um texto ou de passos")
        return self


# Tetos do que a IA escreve, em caracteres. A limpeza (`formulator/limpeza.py`) corta no limite;
# o schema garante que nada maior chegue à tela nem ao banco.
TIPO_MAX_CARACTERES = 80
ITEM_MAX_CARACTERES = 220
SINAIS_MAX = 5
PASSOS_MIN = 2
PASSOS_MAX = 4

ItemDaIA = Annotated[str, Field(min_length=1, max_length=ITEM_MAX_CARACTERES)]


class ExplicacaoIA(BaseModel):
    """O que a IA escreveu sobre a mensagem, já limpo: sem link, e-mail, telefone nem HTML.

    É texto livre escrito a partir da mensagem e pode repetir trechos dela (um nome, um valor).
    Por isso segue no banco a mesma regra do `texto_input`: só com dono, e só pela janela do
    histórico (ADR-0020).
    """

    model_config = ConfigDict(frozen=True)

    tipo: str = Field(min_length=1, max_length=TIPO_MAX_CARACTERES)
    sinais: tuple[ItemDaIA, ...] = Field(max_length=SINAIS_MAX)
    o_que_fazer: tuple[ItemDaIA, ...] = Field(min_length=PASSOS_MIN, max_length=PASSOS_MAX)


# ── Print da conversa (fatia 9, ADR-0023) ────────────────────────────────────────────────────
# O conjunto fechado que a leitura preenche. Fechado de propósito: nada de texto livre sobre o
# remetente — é o que deixa o contexto ser guardado, mostrado e mandado à IA sem levar nome nem
# número de ninguém.

Canal = Literal["whatsapp", "sms", "email", "instagram", "outro", "nao_identificado"]
SimNao = Literal["sim", "nao"]
SimNaoIncerto = Literal["sim", "nao", "nao_da_para_saber"]
QuemMandou = Literal["contato", "pessoa", "nao_da_para_saber"]
"""`contato`: o que a pessoa recebeu. `pessoa`: o que ela mesma enviou na conversa."""


class ContextoDoPrint(BaseModel):
    """O que o print mostra além do texto. Revela, por exemplo, se a pessoa tem alguém salvo nos
    contatos: segue no banco a regra da `explicacao_ia` — só com dono, zerado na desvinculação."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    canal: Canal
    remetente_salvo: SimNaoIncerto
    aviso_do_app: SimNao
    primeira_mensagem: SimNaoIncerto
    tem_link_visivel: SimNao


class MensagemDoPrint(BaseModel):
    """Um balão da conversa, como a leitura o transcreveu."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    de: QuemMandou
    texto: str = Field(min_length=1)


class LeituraDoPrint(BaseModel):
    """O que lemos no print, para a pessoa conferir: a transcrição e o contexto.

    O motor analisa só o que a pessoa recebeu (`de` = contato ou incerto). O que ela mesma enviou e
    o que escreveu junto no VerifyScan vão só para a IA, como contexto (ADR-0023).
    """

    mensagens: list[MensagemDoPrint] = Field(min_length=1)
    # Correção 9.1: transcrito, o link do print viraria texto pronto para copiar.
    mensagens_para_exibir: list[MensagemDoPrint] = Field(
        min_length=1,
        description=(
            "As mesmas mensagens como a tela mostra: cada link como `[link: domínio]`, cada "
            "telefone como `[telefone]` e cada e-mail como `[e-mail]`."
        ),
    )
    contexto: ContextoDoPrint
    texto_da_pessoa: str | None = Field(
        default=None, description="O que a pessoa digitou junto com o print, se digitou."
    )


class SolicitacaoAnalisePrint(BaseModel):
    """Corpo de `POST /api/analises/imagem`: JSON com a imagem em base64 (ADR-0023).

    JSON, e não multipart: o `UploadFile` do Starlette grava em arquivo temporário acima de 1 MB,
    e a imagem não pode tocar o disco (invariante 2). O tamanho é limitado na rota, antes do parse.
    """

    model_config = ConfigDict(extra="forbid")

    imagem_base64: str = Field(description="PNG, JPEG ou WebP, em base64, sem o prefixo `data:`.")
    texto: str | None = Field(
        default=None, description="O que a pessoa escreveu junto, se escreveu. Vai só para a IA."
    )


class SolicitacaoAnalise(BaseModel):
    """Corpo de `POST /api/analises`.

    O tamanho não é limitado aqui, e sim no service: o limite é configurável e a recusa
    precisa sair com uma frase em pt-BR que o usuário entenda, não com o erro de validação
    padrão do FastAPI.
    """

    texto: str = Field(description="A mensagem suspeita, como o usuário a recebeu.")


class RespostaAnalise(BaseModel):
    """O que o usuário recebe: quanto pontuou, em que nível caiu e por quê.

    `score` e `fatores` são sempre do motor. `nivel_risco` é o final: o maior entre o do motor e
    o sugerido pela IA (ADR-0020).
    """

    score: int
    nivel_risco: NivelRisco
    fatores: list[Fator]
    # Fatia 8 (ADR-0022): substitui `urls_analisadas`, que trazia o link inteiro, pronto para
    # copiar. Mudança de contrato; o único cliente é o frontend deste repositório.
    links: list[LinkDaMensagem] = Field(
        default_factory=list,
        description="Um item por domínio, na ordem em que apareceu: o domínio e o que se achou.",
    )

    # Campos aditivos da fatia 6 (ADR-0020).
    nivel_motor: NivelRisco = Field(description="O nível que o motor deu sozinho.")
    nivel_ia: NivelRisco | None = Field(
        default=None, description="O nível sugerido pela IA; `null` quando ela não entrou."
    )
    orientacao: Orientacao = Field(description="A resposta fixa do nível final (plano B).")
    explicacao_ia: ExplicacaoIA | None = Field(
        default=None,
        description="Tipo, sinais e passos escritos pela IA para esta mensagem, já limpos.",
    )

    # As flags são a face visível das invariantes 3 e 4: a análise nunca falha por causa da IA
    # nem das APIs externas — degrada e avisa.
    explicacao_indisponivel: bool = Field(
        default=True,
        description=(
            "`true` sempre que a resposta saiu sem a explicação da IA: desligada, fora do ar, "
            "acima do teto de tempo ou com uma resposta inválida (RNF08), ou com a explicação "
            "descartada na limpeza. A tela mostra então o plano B do nível final. Com "
            "`nivel_ia` preenchido, a IA deu o nível e só a explicação foi descartada."
        ),
    )
    verificacao_externa_indisponivel: bool = Field(
        default=False,
        description="`true` quando VirusTotal / Safe Browsing não responderam (RNF09).",
    )

    # Campo aditivo da fatia 9 (ADR-0023): só no caminho de imagem.
    leitura_do_print: LeituraDoPrint | None = Field(
        default=None,
        description="A transcrição e o contexto do print, para a pessoa conferir. `null` no texto.",
    )

    # Campo aditivo da fatia 4 (ADR-0015): quem não o conhece, ignora. Diz à tela se pode
    # afirmar "foi salva no seu histórico" — a frase só é verdade quando o registro gravou o dono.
    salva_no_historico: bool = Field(
        default=False,
        description=(
            "`true` só quando a análise foi gravada ligada à conta de quem está logado. Sem "
            "sessão, com sessão vencida ou com o registro descartado, `false`."
        ),
    )

    # Campo aditivo da fatia 5 (ADR-0018): a tela só diz "salva com a mensagem" quando é verdade.
    texto_salvo: bool = Field(
        default=False,
        description=(
            "`true` só quando a análise foi gravada com dono e com a mensagem, que fica no "
            "histórico pela janela de `HISTORICO_DIAS`. Anônima ou com o registro descartado, "
            "`false`."
        ),
    )
