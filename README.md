# VerifyScan

**Plataforma de Detecção de Golpes com Inteligência Artificial**

RFC — Request for Comments | Engenharia de Software — Católica SC

---

## Identificação

| Campo | Informação |
|-------|-----------|
| Título do Projeto | VerifyScan — Plataforma de Detecção de Golpes com IA |
| Linha do Projeto | Web / IA |
| Autor | Walter Theodoro Butenes Alves |
| Data da Proposta | Maio de 2025 |
| Versão | 1.0 |

---

## 1. Visão do Produto e Impacto

### 1.1 Contexto e Problema

O Brasil é um dos países mais afetados por fraudes digitais no mundo. Golpes chegam por WhatsApp, SMS, e-mail, PIX, boletos falsos e lojas online fraudulentas, atingindo milhões de brasileiros todos os anos.

O problema central é que a maioria das pessoas não possui ferramentas acessíveis para verificar rapidamente se uma situação é segura. As alternativas atuais são todas fragmentadas e manuais:

- Pesquisar no Google — lento, exige experiência digital
- Perguntar para alguém — nem sempre disponível ou confiável
- Consultar o Reclame Aqui — requer saber o que procurar
- Ignorar o risco — e torcer para não ser golpe

Grupos mais vulneráveis, como idosos e pessoas com menor letramento digital, são os mais prejudicados pela ausência de uma ferramenta simples e centralizada.

> *"Isso é golpe?" — uma pergunta que milhões de brasileiros fazem todos os dias sem ter uma ferramenta dedicada para respondê-la.*

---

### 1.2 Origem da Demanda e Evidências

A demanda surge de um problema amplamente documentado e sentido pela população brasileira. Segundo dados do Mapa da Fraude (ClearSale, 2023), o Brasil registrou mais de 4 milhões de tentativas de fraude digital só no primeiro semestre de 2023.

Pesquisas informais com colegas, familiares e redes sociais revelam um padrão recorrente: pessoas recebem mensagens suspeitas e não sabem como verificar se é golpe sem a ajuda de alguém mais experiente. O crescimento de grupos no WhatsApp e perfis dedicados a alertar sobre golpes demonstra o interesse real do público por esse tipo de ferramenta.

---

### 1.3 Análise de Soluções Existentes (Benchmark)

| Solução | Pontos Fortes | Limitações |
|---------|--------------|------------|
| Reclame Aqui | Base robusta de relatos de usuários | Sem IA, busca manual, não analisa links ou prints |
| Dfndr Security | Detecta links maliciosos no celular em tempo real | Sem análise de contexto textual |
| VirusTotal | Análise técnica profunda de URLs e arquivos | Interface técnica, inacessível para leigos |
| Phishtank | Base colaborativa de phishing atualizada | Sem suporte a linguagem natural |
| Google Safe Browsing | Integrado a navegadores, ampla cobertura | Não analisa contexto, apenas URLs conhecidas |

**Diferencial:** o VerifyScan é a única solução que combina análise de linguagem natural + verificação de links e domínios + leitura de imagens via OCR + consulta a bases de reputação externas + resposta acessível ao usuário leigo, tudo em um único fluxo.

---

### 1.4 Público-Alvo

| Perfil | Justificativa |
|--------|--------------|
| Idosos (55+) | Grupo mais vulnerável, menor letramento digital, alvos frequentes de golpes por WhatsApp |
| Adultos em geral | Expostos a golpes de PIX, boletos falsos e lojas fraudulentas |
| Pequenos empreendedores | Vítimas frequentes de fraudes de fornecedores e pagamentos |
| Qualquer pessoa | Que receba uma comunicação suspeita e precise de validação rápida |

---

### 1.5 Objetivos do Projeto

**Objetivo Geral**

Desenvolver uma plataforma web acessível que permita a qualquer pessoa verificar, de forma rápida e simples, se está diante de uma tentativa de golpe digital.

**Objetivos Específicos**

- Implementar um pipeline de análise heurística próprio capaz de processar texto, URLs, e-mails e imagens em busca de indicadores de fraude
- Integrar bases externas de reputação (VirusTotal, Google Safe Browsing) para enriquecer a análise
- Utilizar OCR para extrair e analisar texto contido em prints enviados pelo usuário
- Gerar uma pontuação de risco (baixo / médio / alto) com explicação clara gerada por IA
- Entregar uma interface web simples e acessível mesmo para usuários com pouca experiência digital

---

### 1.6 Métricas de Sucesso (KPIs)

| Métrica | Meta |
|---------|------|
| Tempo de resposta da análise | < 30 segundos por consulta |
| Precisão na identificação de golpes | > 85% em testes com casos reais |
| Usuários simultâneos suportados | Mínimo 100 sem degradação |
| NPS (satisfação) | > 40 nos primeiros testes com usuários |

---

## 2. Engenharia de Requisitos

### 2.1 Personas

**Persona 1 — Dona Maria, 67 anos**
Aposentada, usa WhatsApp todos os dias para falar com a família. Recebe frequentemente mensagens de promoções, cobranças e pedidos de PIX de remetentes desconhecidos. Não sabe distinguir sites falsos de verdadeiros. Seu principal objetivo é não perder dinheiro nem passar vergonha com a família por ter caído em um golpe.

**Persona 2 — Carlos, 34 anos**
Analista de RH, usa o celular e o computador no trabalho. Já recebeu e-mails de phishing se passando pelo banco. Tem algum letramento digital mas não é expert em segurança. Quer uma ferramenta rápida para verificar links suspeitos sem precisar abrir o VirusTotal e interpretar resultados técnicos.

**Persona 3 — João, 45 anos**
Dono de uma pequena loja. Já foi vítima de fraude de fornecedor. Recebe propostas comerciais por e-mail e WhatsApp e não tem tempo nem conhecimento para verificar a procedência de cada uma.

---

### 2.2 Casos de Uso Principais

- Enviar texto suspeito para análise
- Enviar link ou URL para verificação
- Enviar print (imagem) de mensagem suspeita
- Visualizar resultado da análise com pontuação de risco e explicação
- Consultar histórico de análises anteriores (usuário autenticado)

---

### 2.3 Requisitos Funcionais

| ID | Descrição |
|----|-----------|
| RF01 | O sistema deve permitir que o usuário insira texto livre descrevendo a situação suspeita |
| RF02 | O sistema deve permitir que o usuário envie um link ou URL para análise |
| RF03 | O sistema deve permitir que o usuário envie uma imagem (print) para análise |
| RF04 | O sistema deve extrair o texto contido em imagens via OCR |
| RF05 | O sistema deve identificar e extrair URLs presentes no texto e nas imagens |
| RF06 | O sistema deve verificar URLs contra bases de dados de phishing e malware |
| RF07 | O sistema deve analisar padrões heurísticos no texto (urgência, premiação, solicitação de dados, PIX) |
| RF08 | O sistema deve verificar a reputação de domínios via APIs externas (VirusTotal, Google Safe Browsing) |
| RF09 | O sistema deve gerar uma pontuação de risco: Baixo, Médio ou Alto |
| RF10 | O sistema deve exibir uma explicação em linguagem simples sobre os fatores que levaram ao resultado |
| RF11 | O sistema deve permitir que o usuário crie uma conta e faça login |
| RF12 | O sistema deve armazenar o histórico de análises do usuário autenticado |

---

### 2.4 Requisitos Não Funcionais

| ID | Descrição |
|----|-----------|
| RNF01 | O tempo de resposta da análise deve ser inferior a 30 segundos |
| RNF02 | O sistema deve suportar no mínimo 100 usuários simultâneos sem degradação |
| RNF03 | O sistema deve utilizar autenticação segura com senha criptografada (bcrypt) |
| RNF04 | A comunicação entre frontend e backend deve ser realizada via HTTPS |
| RNF05 | O sistema deve ser acessível em dispositivos móveis (design responsivo) |
| RNF06 | As imagens enviadas pelo usuário não devem ser armazenadas após a análise |
| RNF07 | O sistema deve estar disponível no mínimo 95% do tempo (uptime) |

---

### 2.5 Regras de Negócio

- Usuários não autenticados podem realizar até 1 análise por sessão
- Usuários autenticados têm acesso a análises ilimitadas e ao histórico
- O algoritmo de análise deve ser executado antes da chamada à IA — a IA recebe apenas o resultado estruturado, não o conteúdo bruto
- Nenhum conteúdo enviado pelo usuário deve ser usado para treinar modelos de IA externos
- Análises sem conteúdo identificável devem retornar mensagem de erro informativo

---

### 2.6 Fora do Escopo

- O sistema não realizará bloqueio automático de sites ou URLs
- O sistema não atuará como antivírus nem fará análise de arquivos executáveis
- Não haverá integração nativa com WhatsApp na versão inicial (prevista para versões futuras)
- O sistema não armazenará conteúdo de terceiros citados nas mensagens analisadas
- Não será realizada análise forense de dispositivos

---

## 3. Fluxos e Comportamento do Sistema

### 3.1 Fluxo Principal

```
1. Usuário descreve a situação suspeita (texto livre)
         ↓
2. Opcionalmente, anexa link, print ou e-mail
         ↓
3. OCRProcessor extrai texto de imagens (se houver)
         ↓
4. URLExtractor identifica e normaliza todas as URLs
         ↓
5. TextAnalyzer aplica regras heurísticas no texto
         ↓
6. DomainAnalyzer verifica typosquatting, idade, TLD
         ↓
7. URLChecker consulta VirusTotal e Google Safe Browsing
         ↓
8. EmailAnalyzer analisa remetente e corpo (se for e-mail)
         ↓
9. ScoringEngine agrega tudo e calcula a pontuação de risco
         ↓
10. AIFormulator recebe o resultado estruturado e gera a resposta
         ↓
11. Usuário recebe: nível de risco + explicação + recomendações
```

### 3.2 Fluxos Alternativos

- **Erro na análise de imagem:** se o OCR não identificar texto legível, o sistema notifica o usuário e solicita descrição em texto
- **URL inacessível:** o sistema analisa apenas o domínio e padrões da URL, informando a limitação
- **API externa indisponível:** a análise continua com as regras heurísticas próprias, sinalizando que a verificação externa não foi possível

---

## 4. Mockups e Experiência do Usuário (UX)

### 4.1 Fluxo de Navegação

```
Página Inicial → Área de Análise → Resultado → (Opcional) Login / Cadastro → Histórico
```

### 4.2 Telas Principais

**Tela 1 — Página Inicial**
Campo central para inserir texto suspeito e botões para anexar link, imagem ou e-mail. Linguagem simples e direta, com call-to-action "Analisar agora".

**Tela 2 — Análise em Andamento**
Feedback visual mostrando as etapas em execução: "Extraindo URLs...", "Verificando domínios...", "Analisando padrões...".

**Tela 3 — Resultado da Análise**
Nível de risco com destaque visual (verde / amarelo / vermelho), explicação em linguagem simples dos fatores identificados e recomendações de ação.

**Tela 4 — Login / Cadastro**
Formulário simples com e-mail e senha. Dá acesso ao histórico de análises.

**Tela 5 — Histórico**
Lista de análises anteriores com data, resumo e resultado. Disponível apenas para usuários autenticados.

---

## 5. Arquitetura do Sistema

### 5.1 Visão Geral (C4 — Nível 1: Contexto)

| Ator / Sistema | Tipo | Interação |
|---------------|------|-----------|
| Usuário | Pessoa | Envia texto, links e imagens; recebe resultado da análise |
| VerifyScan | Sistema central | Processa, analisa e retorna o parecer de risco |
| VirusTotal API | Sistema externo | Verificação de URLs e domínios contra bases de malware |
| Google Safe Browsing | Sistema externo | Verificação de URLs conhecidas como phishing |
| API de IA (LLM) | Sistema externo | Geração da explicação em linguagem natural |

---

### 5.2 Containers (C4 — Nível 2)

| Container | Tecnologia | Responsabilidade |
|-----------|-----------|-----------------|
| Frontend Web | React / Next.js | Interface do usuário, envio de dados, exibição de resultados |
| API Backend | Python / FastAPI | Orquestração do pipeline de análise |
| Módulo de Análise Heurística | Python | TextAnalyzer, URLExtractor, DomainAnalyzer, EmailAnalyzer |
| Módulo OCR | Tesseract | Extração de texto de imagens enviadas pelo usuário |
| ScoringEngine | Python | Agrega resultados de todos os módulos e calcula a pontuação |
| AIFormulator | LLM API | Transforma o resultado estruturado em resposta acessível |
| Banco de Dados | PostgreSQL | Usuários e histórico de análises |
| Cache | Redis | Resultados de URLs já verificadas (evita chamadas repetidas) |

---

### 5.3 O Pipeline de Análise em Detalhe (C4 — Nível 3)

Este é o coração do projeto: um algoritmo próprio com módulos independentes. Cada módulo analisa um aspecto diferente do conteúdo e retorna uma pontuação parcial. O ScoringEngine agrega tudo no final.

---

#### 5.3.1 TextAnalyzer — Análise de Padrões no Texto

Aplica regras heurísticas sobre o texto enviado, procurando padrões linguísticos característicos de golpes. O algoritmo percorre o texto com expressões regulares e correspondência de termos. Cada padrão encontrado adiciona pontos ao score final.

| Categoria | Exemplos de padrões detectados | Peso |
|-----------|-------------------------------|------|
| Urgência | "clique agora", "expira em", "últimas horas", "prazo vencendo" | +10 |
| Personificação de marca | "Banco do Brasil informa", "Correios — encomenda retida" | +15 |
| Ameaça / bloqueio | "sua conta será suspensa", "evite o bloqueio", "última notificação" | +15 |
| Prêmio falso | "você foi selecionado", "parabéns, você ganhou", "resgate seu prêmio" | +20 |
| Solicitação financeira | "transfira", "faça um PIX de", "deposite", "comprovante de pagamento" | +25 |
| Dados pessoais | "informe seu CPF", "confirme sua senha", "dados bancários" | +25 |

---

#### 5.3.2 URLExtractor — Extração de Links

Antes de analisar qualquer URL, é preciso encontrá-las no texto. O URLExtractor usa expressões regulares para identificar todos os links presentes, incluindo:

- URLs completas (`https://...`)
- URLs sem protocolo (`www.site.com`)
- URLs encurtadas (`bit.ly/xxxxx`, `t.co/xxxxx`)
- URLs embutidas em textos ("acesse aqui: site.com")

Após a extração, cada URL é normalizada e encaminhada ao URLChecker e ao DomainAnalyzer.

---

#### 5.3.3 DomainAnalyzer — Análise do Domínio

Mesmo sem consultar APIs externas, muitas fraudes são detectáveis só pela análise do domínio. O módulo aplica quatro verificações:

**Typosquatting**
Compara o domínio encontrado com uma lista de marcas e instituições conhecidas (Bradesco, Itaú, Caixa, Correios, Netflix, etc.) usando o algoritmo de distância de Levenshtein. Um domínio como `bradesc0.com` ou `itau-online.net` é identificado como suspeito por ter distância de edição baixa em relação ao domínio legítimo.

**Subdomínio enganoso**
Verifica se uma marca conhecida aparece como subdomínio mas não como domínio principal:
```
bradesco.conta-segura.com  →  domínio real = conta-segura.com  →  SUSPEITO
```

**TLD de alto risco**
Domínios com extensões como `.xyz`, `.top`, `.click`, `.tk`, `.pw` têm índice de fraude significativamente maior e somam pontos ao score.

**Idade do domínio**
Consulta WHOIS para verificar quando o domínio foi registrado. Domínios criados há menos de 30 dias recebem pontuação adicional, pois golpistas frequentemente registram domínios novos para cada campanha.

---

#### 5.3.4 URLChecker — Verificação em Bases Externas

Após a análise própria do domínio, as URLs são enviadas para verificação externa:

**VirusTotal API**
Envia a URL para o VirusTotal, que a verifica contra mais de 70 engines de segurança. A pontuação aumenta proporcionalmente ao número de detecções:

| Resultado | Pontuação |
|-----------|-----------|
| 0 detecções | Sem pontuação adicional |
| 1–2 detecções | +20 (pode ser falso positivo, mas sinaliza atenção) |
| 3+ detecções | +40 (forte indicador de URL maliciosa) |

**Google Safe Browsing API**
API gratuita do Google que verifica se a URL está na base de phishing e malware conhecidos. Retorno positivo soma +40 ao score.

**Cache de resultados**
Para evitar chamadas repetidas às APIs, os resultados são armazenados em cache no Redis por URL (hash SHA-256). Se a mesma URL já foi verificada recentemente, o resultado em cache é reutilizado sem nova chamada à API.

---

#### 5.3.5 OCRProcessor — Análise de Prints e Imagens

Muitos golpes chegam como prints de conversa de WhatsApp, SMS ou capturas de tela. O OCRProcessor resolve isso:

1. O usuário envia a imagem
2. O Tesseract OCR processa a imagem e extrai o texto visível
3. O texto extraído é encaminhado ao TextAnalyzer
4. URLs encontradas são encaminhadas ao URLExtractor → URLChecker → DomainAnalyzer
5. O resultado é tratado exatamente como se o usuário tivesse digitado o texto

O OCR funciona como uma ponte — converte imagem em texto para que os outros módulos analisem normalmente. Caso o texto extraído seja insuficiente, o sistema informa o usuário.

---

#### 5.3.6 EmailAnalyzer — Análise de E-mails

Quando o usuário cola o conteúdo de um e-mail suspeito, o módulo realiza verificações específicas:

**Análise do remetente**
Extrai o endereço do remetente e verifica se o domínio corresponde à instituição declarada:
```
"Suporte Bradesco" <noreply@bradesco.atendimento-segura.com>
→ domínio real = atendimento-segura.com
→ não é bradesco.com.br  →  SUSPEITO
```

**Validação SPF/DKIM**
Se o usuário colar o cabeçalho completo do e-mail, o sistema verifica se as entradas SPF e DKIM são válidas para o domínio declarado. E-mails legítimos de grandes instituições quase sempre passam nessas validações.

**Análise do corpo**
O texto do e-mail é passado pelo TextAnalyzer, aplicando todas as regras heurísticas.

**Links no corpo**
Todos os links encontrados no corpo do e-mail são extraídos pelo URLExtractor e verificados pelo URLChecker e DomainAnalyzer.

---

#### 5.3.7 ScoringEngine — Cálculo do Risco Final

Agrega os resultados de todos os módulos e calcula a pontuação final:

| Fator identificado | Pontuação |
|--------------------|-----------|
| Palavra de urgência | +10 |
| TLD de alto risco | +15 |
| Personificação de marca | +15 |
| Ameaça de bloqueio | +15 |
| Prêmio ou oferta falsa | +20 |
| Domínio criado há menos de 30 dias | +20 |
| URL flagrada no VirusTotal (1–2 engines) | +20 |
| Solicitação de PIX ou dados bancários | +25 |
| Falha na validação SPF/DKIM | +25 |
| Subdomínio enganoso | +30 |
| Remetente de e-mail suspeito | +30 |
| Typosquatting identificado | +35 |
| URL flagrada no VirusTotal (3+ engines) | +40 |
| URL flagrada no Google Safe Browsing | +40 |

**Classificação final:**

| Pontuação | Nível de risco | Interpretação |
|-----------|---------------|---------------|
| 0–30 | 🟢 Risco BAIXO | Provavelmente seguro — nenhum indicador relevante encontrado |
| 31–60 | 🟡 Risco MÉDIO | Atenção recomendada — alguns indicadores presentes |
| 61+ | 🔴 Risco ALTO | Forte indicativo de golpe — múltiplos fatores confirmados |

---

#### 5.3.8 AIFormulator — Geração da Resposta

A IA não participa da análise. Ela recebe apenas o resultado estruturado do ScoringEngine e o transforma em uma explicação clara, em português acessível.

**Entrada enviada para a IA:**
```json
{
  "score": 75,
  "risco": "ALTO",
  "fatores": [
    "URL flagrada no VirusTotal por 5 engines",
    "Texto contém solicitação de PIX",
    "Domínio registrado há 3 dias",
    "Typosquatting detectado: bradesc0.com"
  ]
}
```

**Resposta gerada para o usuário:**
```
Risco ALTO — Esta mensagem apresenta fortes indicadores de golpe.

Identificamos os seguintes problemas:
• O link foi marcado como perigoso por 5 sistemas de segurança independentes
• Há uma solicitação de pagamento via PIX, prática comum em golpes
• O site foi criado há apenas 3 dias
• O endereço do site imita o nome de uma instituição conhecida

Recomendação: não clique no link, não realize nenhum pagamento e não
informe dados pessoais. Bloqueie o remetente e reporte como spam.
```

---

### 5.4 Modelo de Dados

| Entidade | Atributos principais |
|----------|---------------------|
| Usuario | id, email, senha_hash, created_at, plano (gratuito/pago) |
| Analise | id, usuario_id (nullable), texto_input, tipo_input, score_risco, resultado, created_at |
| IndicadorRisco | id, analise_id, tipo (url/texto/dominio/ocr/email), descricao, peso |
| URLVerificada | url_hash, resultado_virustotal, resultado_safebrowsing, cached_at |

---

### 5.5 Stack Tecnológica

| Tecnologia | Uso | Justificativa |
|------------|-----|---------------|
| React / Next.js | Frontend | Ecossistema maduro, responsivo, boa experiência mobile |
| Python / FastAPI | Backend | Suporte nativo a OCR, processamento de texto e integrações de IA |
| Tesseract OCR | Extração de texto de imagens | Open source, suporte ao português |
| VirusTotal API | Verificação de URLs | Base ampla, API gratuita disponível |
| Google Safe Browsing | Verificação de URLs | API gratuita e confiável, mantida pelo Google |
| PostgreSQL | Banco de dados | Relacional, robusto, suporte a JSON |
| Redis | Cache de resultados | Evita chamadas repetidas às APIs externas |
| LLM API | Formulação da resposta | Gera explicações claras em português a partir do resultado estruturado |

---

## 6. Segurança e Privacidade

- Autenticação com senha criptografada via bcrypt
- Tokens de sessão JWT com expiração
- Comunicação exclusivamente via HTTPS
- Validação e sanitização de todos os inputs (proteção contra injeção e XSS)
- Rate limiting nas rotas da API para prevenir abuso
- Imagens enviadas não são armazenadas após o processamento

### 6.1 Privacidade e LGPD

| Dado Coletado | Finalidade | Armazenamento |
|--------------|-----------|---------------|
| E-mail e senha | Autenticação | Permanente (senha hasheada) |
| Texto enviado | Histórico do usuário | Permanente (somente usuários autenticados) |
| Imagens enviadas | Processamento OCR | Temporário — descartado após a análise |
| URLs analisadas | Cache de resultados | Anonimizado por hash SHA-256 |

O usuário poderá solicitar a exclusão de sua conta e de todos os seus dados a qualquer momento, em conformidade com a LGPD (Lei nº 13.709/2018).

---

## 7. Planejamento do Projeto

| Marco | Descrição | Prazo |
|-------|-----------|-------|
| M1 | Setup do ambiente, estrutura do repositório, definição da stack | Semana 1–2 |
| M2 | Implementação do TextAnalyzer e URLExtractor | Semana 3–4 |
| M3 | Implementação do DomainAnalyzer (Levenshtein, WHOIS, TLD) | Semana 5–6 |
| M4 | Integração OCR (OCRProcessor com Tesseract) | Semana 7–8 |
| M5 | Integração das APIs externas (VirusTotal, Safe Browsing) + cache Redis | Semana 9–10 |
| M6 | EmailAnalyzer + ScoringEngine completo | Semana 11–12 |
| M7 | AIFormulator + integração com LLM | Semana 13 |
| M8 | Frontend completo (interface web) | Semana 14–16 |
| M9 | Testes com casos reais, ajustes de precisão e UX | Semana 17–18 |
| M10 | Documentação final e apresentação | Semana 19–20 |

---

## 8. Referências

- ClearSale. Mapa da Fraude 2023. Disponível em: https://mkt.clear.sale/mapa-da-fraude
- VirusTotal API Documentation. Disponível em: https://developers.virustotal.com
- Google Safe Browsing API. Disponível em: https://developers.google.com/safe-browsing
- Tesseract OCR. Disponível em: https://github.com/tesseract-ocr/tesseract
- Algoritmo de Levenshtein — distância de edição entre strings
- OWASP Top 10. Disponível em: https://owasp.org/www-project-top-ten/
- Lei Geral de Proteção de Dados (LGPD) — Lei nº 13.709/2018
- FastAPI Documentation. Disponível em: https://fastapi.tiangolo.com

---

## Estrutura do Repositório

```
verifyscan/
├── docs/               # Diagramas e decisões de arquitetura
├── frontend/           # Interface web (React / Next.js)
├── backend/
│   ├── analyzers/      # TextAnalyzer, URLExtractor, DomainAnalyzer, EmailAnalyzer
│   ├── ocr/            # OCRProcessor (Tesseract)
│   └── scoring/        # ScoringEngine + AIFormulator
└── README.md
```

---

*VerifyScan — porque ninguém deveria cair em golpe por falta de informação.*
