// Alerta de orçamento da assinatura (ADR-0029). O crédito do Azure for Students é de US$ 100 no
// total, e o limite de gasto desativa a assinatura quando ele acaba: o site sairia do ar sem
// aviso. Este orçamento não bloqueia nada; só manda e-mail quando o gasto do ano passa de
// US$ 60 e de US$ 85.
//
// Fica separado do main.bicep porque é da assinatura, e não do grupo de recursos. O e-mail vai
// e o valor do crédito vão na linha de comando, não em arquivo versionado:
//
//   az deployment sub create -l chilecentral -f infra/orcamento.bicep -p emailDeAviso=<e-mail> valorDoCredito=<valor>
//
// O valor é na MOEDA DA ASSINATURA, que aqui é o real (BRL), e não o dólar: é o total do crédito
// como o portal do Azure o mostra. Os avisos são porcentagens dele, então 60% e 85% correspondem
// a US$ 60 e US$ 85 dos US$ 100.
//
// A assinatura de estudante pode não aceitar orçamento (a API de custos recusa esse tipo de
// oferta). Se este comando for recusado, o ADR-0029 traz as datas de conferência do saldo.

targetScope = 'subscription'

@description('Quem recebe o aviso.')
param emailDeAviso string

@description('O total do crédito, na moeda da assinatura (BRL).')
param valorDoCredito int

@description('Primeiro dia do período. O Azure exige o dia 1º de um mês.')
param inicio string = '2026-11-01'

resource orcamento 'Microsoft.Consumption/budgets@2023-11-01' = {
  name: 'verifyscan-credito'
  properties: {
    category: 'Cost'
    // O valor é o do crédito; os avisos são porcentagens dele: 60% e 85%.
    amount: valorDoCredito
    timeGrain: 'Annually'
    timePeriod: {
      startDate: inicio
    }
    notifications: {
      passouDe60: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 60
        thresholdType: 'Actual'
        contactEmails: [emailDeAviso]
      }
      passouDe85: {
        enabled: true
        operator: 'GreaterThan'
        threshold: 85
        thresholdType: 'Actual'
        contactEmails: [emailDeAviso]
      }
    }
  }
}
