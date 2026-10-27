# Casos escritos pelo Walter — modelo

Os 161 casos de `casos/` foram escritos pelo Claude, e a IA que os analisa também é um Claude
(ADR-0021, viés de autoria). Estes 20 servem de contraste: as métricas saem separadas por autor.

**Como preencher:** 10 golpes e 10 legítimas, em texto livre, do jeito que a mensagem chegaria.
Escreva de cabeça ou inspirado em algo que você viu, mas **sem colar mensagem real**: pode trocar
nome, número e link à vontade, eu anonimizo na conversão (nome vira `[NOME]`, telefone
`[TELEFONE]`, e-mail `[EMAIL]`, link vai para o domínio `.example`). Valor em reais pode ficar.

Se ficar em dúvida se um caso é golpe ou legítimo, marque `ambígua`: ele não entra no corpus,
mas fica anotado.

Na conversão, cada um vira um YAML com `autor: walter`, `fonte: sintetico` e passa pelo mesmo
sorteio (`uv run python -m tools.sortear_divisao`), que só divide os casos novos.

---

## Golpes

### 1
- **Canal:** (sms · whatsapp · email · notificacao · print)
- **Inspirado em:** (opcional: que tipo de golpe, onde você viu o alerta)
- **Mensagem:**

```
```

### 2
- **Canal:**
- **Inspirado em:**
- **Mensagem:**

```
```

<!-- copie o bloco acima até o 10 -->

## Legítimas

### 1
- **Canal:**
- **Por que é difícil:** (opcional: urgência de verdade, cobrança real, código de verificação…)
- **Mensagem:**

```
```

### 2
- **Canal:**
- **Por que é difícil:**
- **Mensagem:**

```
```

<!-- copie o bloco acima até o 10 -->
