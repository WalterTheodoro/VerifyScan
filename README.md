
<div align="center">

#  VerifyScan

**Plataforma de detecção de golpes com Inteligência Artificial**

</div>

---

##  O que é o VerifyScan?

O **VerifyScan** é um SaaS que permite que qualquer pessoa verifique se está diante de um possível golpe digital. O usuário descreve a situação suspeita em linguagem natural, anexa prints, links ou e-mails, e a IA analisa tudo — verificando URLs, consultando bases de reclamações, fóruns e outros indicadores — retornando um parecer claro sobre o nível de risco.

> *"Isso é golpe?" — uma pergunta que milhões de brasileiros fazem todos os dias sem ter uma ferramenta dedicada para respondê-la.*

---

##  O Problema

O Brasil é um dos países mais afetados por fraudes digitais. Os golpes chegam por WhatsApp, SMS, e-mail, PIX, boletos falsos e lojas online fraudulentas. O problema: a maioria das pessoas não tem como verificar rapidamente se uma situação é segura.

As alternativas atuais são todas **fragmentadas e manuais**:

-  Pesquisar no Google — lento, exige experiência digital
-  Perguntar para alguém — nem sempre disponível ou confiável
-  Consultar o Reclame Aqui — requer saber o que procurar
-  Ignorar o risco — e torcer para não ser golpe

O VerifyScan resolve isso com **uma única interface simples e acessível**.

---

##  Como funciona

```
1. Usuário descreve a situação (texto livre)
      ↓
2. Anexa evidências (link, print, e-mail, texto suspeito)
      ↓
3. IA analisa: linguagem, URLs, domínios, Reclame Aqui, fóruns...
      ↓
4. Retorna um parecer claro: risco baixo / médio / alto + explicação
```

---

##  Público-alvo

| Perfil | Por quê? |
|--------|----------|
| Idosos (55+) | Grupo mais vulnerável, menor letramento digital |
| Adultos em geral | Expostos a golpes de PIX, boletos, lojas falsas |
| Pequenos empreendedores | Vitimas frequentes de fraudes de fornecedores |
| Qualquer pessoa | Que receba uma comunicação suspeita e precise de validação |

---

##  Modelo de negócio

| Plano | Descrição |
|-------|-----------|
|  Gratuito | 1 análise por e-mail |
|  Pago | Análises ilimitadas + funcionalidades extras (a definir) |

---

##  Stack (prevista)

> *Em definição. Será atualizado conforme o projeto avança.*

- **Frontend:** Web (a definir)
- **Backend:** a definir
- **IA:** LLM + pipeline de análise de URLs e reputação
- **Integrações:** Reclame Aqui, VirusTotal, bases de phishing, fóruns

---

##  Benchmarking

| Solução | Pontos fortes | Limitação vs VerifyScan |
|---------|--------------|------------------------|
| Reclame Aqui | Base robusta de relatos | Sem IA, busca manual, não analisa links |
| Dfndr Security | Detecta links maliciosos no celular | Sem análise de contexto textual |
| VirusTotal | Análise técnica profunda de URLs | Interface técnica, inacessível para leigos |
| Phishtank | Base colaborativa de phishing | Sem suporte a linguagem natural |

**Diferencial:** o VerifyScan é a única solução que combina análise de linguagem natural + verificação de links + consulta a bases de reputação + resposta acessível ao usuário leigo, tudo em um único fluxo.

---

##  KPIs do projeto

| Métrica | Meta |
|---------|------|
| Tempo de resposta da análise | < 30 segundos por consulta |
| Precisão na identificação de golpes | > 85% em testes com casos reais |
| Usuários simultâneos suportados | Mínimo 100 sem degradação |
| Conversão freemium → pago | Mínimo 5% dos usuários gratuitos |
| NPS (satisfação) | > 40 nos primeiros testes |

---

##  Estrutura do repositório

```
verifyscan/
├── docs/           # Documentação (RFC, diagramas, decisões)
├── frontend/       # Interface web
├── backend/        # API e lógica de negócio
├── ai/             # Pipeline de análise com IA
└── README.md
```

---

## 📄 Documentação

- [`docs/RFC_VerifyScan_v1.0.docx`](docs/RFC_VerifyScan_v1.0.docx) — Request for Comments completo (proposta acadêmica)

---

##  Autor

Walter Theodoro Butenes Alves

---

<div align="center">
  <sub>VerifyScan — porque ninguém deveria cair em golpe por falta de informação.</sub>
</div>
