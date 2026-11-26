// Infraestrutura de produção do VerifyScan no Azure (ADR-0029). Tudo o que existe na assinatura
// para o site rodar está neste arquivo; nada é criado à mão no portal, exceto os VALORES dos
// segredos no cofre.
//
// Aplicar (o grupo de recursos é criado antes, uma vez, com `az group create`):
//
//   $env:ID_DO_OPERADOR = az ad signed-in-user show --query id -o tsv
//   az deployment group what-if -g rg-verifyscan -p infra/producao.bicepparam
//   az deployment group create  -g rg-verifyscan -p infra/producao.bicepparam
//
// O alerta de orçamento fica em orcamento.bicep, porque é da assinatura e não do grupo.

targetScope = 'resourceGroup'

// ── parâmetros ───────────────────────────────────────────────────────────────────────────────

@description('Região. A política da assinatura só permite cinco; chilecentral é a mais próxima do Brasil com VM barata liberada.')
param regiao string = resourceGroup().location

@description('Tamanho da VM. B2als_v2 (2 vCPU, 4 GB) até o Demo Day; depois, B2ats_v2 (1 GB). Trocar aqui e reaplicar reinicia a VM.')
param tamanhoDaVm string

@description('Rótulo DNS do IP público: o site fica em <rotulo>.<regiao>.cloudapp.azure.com.')
param rotuloDns string

@description('Usuário do sistema que o Azure cria na VM. Ninguém entra com ele: não há senha, a chave privada foi apagada e a porta 22 fica fechada.')
param usuarioDaVm string = 'azureuser'

@description('Chave SSH pública desse usuário. O Azure exige uma na criação.')
param chaveSshPublica string

@description('Id (object id) de quem preenche os segredos no portal. Recebe só o papel de escrever segredos no cofre.')
param idDoOperador string

@description('Repositório do GitHub que pode fazer deploy, como "dono/nome". Maiúsculas e minúsculas contam.')
param repositorioGithub string

@description('Ambiente do GitHub Actions de onde o deploy sai. Só jobs desse ambiente recebem o token.')
param ambienteGithub string

// ── nomes ────────────────────────────────────────────────────────────────────────────────────

// Cofre e conta de armazenamento têm nome único no mundo inteiro: o sufixo sai do id do grupo de
// recursos, então é sempre o mesmo neste grupo e não precisa ser inventado.
var sufixo = uniqueString(resourceGroup().id)

// Papéis prontos do Azure, pelo id (os nomes aparecem no portal).
var papelLerSegredos = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6') // Key Vault Secrets User
var papelEscreverSegredos = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7') // Key Vault Secrets Officer
var papelGravarBlobs = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe') // Storage Blob Data Contributor

// ── rede ─────────────────────────────────────────────────────────────────────────────────────

// Só 80 e 443 entram. Não há regra para a 22: o que não está liberado aqui cai na regra padrão
// do Azure, que nega toda entrada vinda da internet. Deploy e manutenção são por run-command.
resource nsg 'Microsoft.Network/networkSecurityGroups@2024-05-01' = {
  name: 'nsg-verifyscan'
  location: regiao
  properties: {
    securityRules: [
      {
        name: 'entra-http'
        properties: {
          description: 'HTTP: o Caddy redireciona para HTTPS e responde o desafio do certificado.'
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'Internet'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '80'
        }
      }
      {
        name: 'entra-https'
        properties: {
          description: 'HTTPS: o site.'
          priority: 110
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'Internet'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '443'
        }
      }
    ]
  }
}

resource rede 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: 'vnet-verifyscan'
  location: regiao
  properties: {
    addressSpace: {
      addressPrefixes: ['10.20.0.0/24']
    }
    subnets: [
      {
        name: 'snet-vm'
        properties: {
          addressPrefix: '10.20.0.0/27'
          networkSecurityGroup: {
            id: nsg.id
          }
        }
      }
    ]
  }
}

// IP fixo: o endereço do site não muda quando a VM reinicia ou troca de tamanho.
resource ipPublico 'Microsoft.Network/publicIPAddresses@2024-05-01' = {
  name: 'pip-verifyscan'
  location: regiao
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
    publicIPAddressVersion: 'IPv4'
    dnsSettings: {
      domainNameLabel: rotuloDns
    }
  }
}

resource placaDeRede 'Microsoft.Network/networkInterfaces@2024-05-01' = {
  name: 'nic-verifyscan'
  location: regiao
  properties: {
    ipConfigurations: [
      {
        name: 'principal'
        properties: {
          privateIPAllocationMethod: 'Dynamic'
          subnet: {
            id: rede.properties.subnets[0].id
          }
          publicIPAddress: {
            id: ipPublico.id
          }
        }
      }
    ]
  }
}

// ── VM ───────────────────────────────────────────────────────────────────────────────────────

resource vm 'Microsoft.Compute/virtualMachines@2024-07-01' = {
  name: 'vm-verifyscan'
  location: regiao
  // A identidade da própria VM: é com ela que o deploy lê os segredos do cofre e que o backup
  // grava no armazenamento. Não existe senha nem chave para isso em lugar nenhum.
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    hardwareProfile: {
      vmSize: tamanhoDaVm
    }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: 'ubuntu-24_04-lts'
        sku: 'server'
        version: 'latest'
      }
      osDisk: {
        name: 'osdisk-verifyscan'
        createOption: 'FromImage'
        managedDisk: {
          storageAccountType: 'StandardSSD_LRS'
        }
        // O volume do Postgres mora neste disco: se a VM for apagada, o disco fica.
        deleteOption: 'Detach'
      }
    }
    osProfile: {
      computerName: 'verifyscan'
      adminUsername: usuarioDaVm
      // Docker, rotação de log, atualizações automáticas e swap, na primeira subida. Só roda
      // uma vez: o Azure recusa mudar este campo numa VM que já existe.
      customData: loadFileAsBase64('cloud-init.yaml')
      linuxConfiguration: {
        disablePasswordAuthentication: true
        ssh: {
          publicKeys: [
            {
              path: '/home/${usuarioDaVm}/.ssh/authorized_keys'
              keyData: chaveSshPublica
            }
          ]
        }
      }
    }
    securityProfile: {
      securityType: 'TrustedLaunch'
      uefiSettings: {
        secureBootEnabled: true
        vTpmEnabled: true
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: placaDeRede.id
        }
      ]
    }
    // O log da subida da VM, visível no portal sem SSH. Sem conta de armazenamento nossa.
    diagnosticsProfile: {
      bootDiagnostics: {
        enabled: true
      }
    }
  }
}

// ── cofre de segredos ────────────────────────────────────────────────────────────────────────

// Só o cofre e as permissões. Os segredos NÃO são declarados aqui de propósito: reaplicar este
// arquivo sobrescreveria os valores que o Walter colocou pelo portal.
resource cofre 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-vscan-${sufixo}'
  location: regiao
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    // Quem pode o quê é decidido pelos papéis abaixo, e não por uma lista dentro do cofre.
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
}

resource vmLeSegredos 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(cofre.id, vm.id, papelLerSegredos)
  scope: cofre
  properties: {
    description: 'A VM lê os segredos na hora do deploy.'
    roleDefinitionId: papelLerSegredos
    principalId: vm.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource operadorEscreveSegredos 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(cofre.id, idDoOperador, papelEscreverSegredos)
  scope: cofre
  properties: {
    description: 'O Walter preenche os valores dos segredos pelo portal.'
    roleDefinitionId: papelEscreverSegredos
    principalId: idDoOperador
    principalType: 'User'
  }
}

// ── backup ───────────────────────────────────────────────────────────────────────────────────

resource armazenamento 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'stvscan${sufixo}'
  location: regiao
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    // Sem chave de conta: só entra quem tem papel, com a própria identidade.
    allowSharedKeyAccess: false
  }
}

// Sem lixeira de blobs: o aviso de privacidade promete que o que a pessoa apagou some das
// cópias de segurança em até 7 dias, e a lixeira guardaria os arquivos apagados por mais tempo.
resource blobs 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: armazenamento
  name: 'default'
  properties: {
    deleteRetentionPolicy: {
      enabled: false
    }
    containerDeleteRetentionPolicy: {
      enabled: false
    }
  }
}

resource containerDeBackups 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobs
  name: 'backups'
  properties: {
    publicAccess: 'None'
  }
}

// Os 7 dias de retenção são do próprio armazenamento: nenhum script nosso precisa apagar nada.
resource retencao 'Microsoft.Storage/storageAccounts/managementPolicies@2023-05-01' = {
  parent: armazenamento
  name: 'default'
  properties: {
    policy: {
      rules: [
        {
          name: 'apaga-backup-com-mais-de-7-dias'
          enabled: true
          type: 'Lifecycle'
          definition: {
            filters: {
              blobTypes: ['blockBlob']
              prefixMatch: ['${containerDeBackups.name}/']
            }
            actions: {
              baseBlob: {
                delete: {
                  daysAfterModificationGreaterThan: 7
                }
              }
            }
          }
        }
      ]
    }
  }
}

resource vmGravaBackups 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerDeBackups.id, vm.id, papelGravarBlobs)
  scope: containerDeBackups
  properties: {
    description: 'A VM grava e lê o pg_dump diário, só neste container.'
    roleDefinitionId: papelGravarBlobs
    principalId: vm.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── deploy pelo GitHub Actions ───────────────────────────────────────────────────────────────

// A identidade que o GitHub Actions usa. Não tem senha nem segredo de cliente: o GitHub prova
// quem é com um token assinado por ele mesmo (OIDC), e a credencial abaixo diz qual token vale.
resource identidadeDeDeploy 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-verifyscan-deploy'
  location: regiao
}

// Só vale o token de um job do ambiente indicado, neste repositório. Um fork, outra branch sem
// o ambiente ou outro repositório não conseguem entrar.
resource credencialDoGithub 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  parent: identidadeDeDeploy
  name: 'github-${ambienteGithub}'
  properties: {
    issuer: 'https://token.actions.githubusercontent.com'
    subject: 'repo:${repositorioGithub}:environment:${ambienteGithub}'
    audiences: ['api://AzureADTokenExchange']
  }
}

// Papel próprio, com o mínimo: enxergar a VM e executar comando nela. O papel pronto mais próximo
// (Virtual Machine Contributor) também deixaria apagar, desligar e redimensionar a VM.
resource papelDeDeploy 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: guid(resourceGroup().id, 'verifyscan-deploy')
  properties: {
    // O nome de papel é único no diretório inteiro, por isso leva o sufixo.
    roleName: 'VerifyScan - deploy por run-command (${sufixo})'
    description: 'Ver a VM do VerifyScan e executar comando nela. Nada mais.'
    type: 'CustomRole'
    permissions: [
      {
        actions: [
          'Microsoft.Compute/virtualMachines/read'
          'Microsoft.Compute/virtualMachines/instanceView/read'
          'Microsoft.Compute/virtualMachines/runCommand/action'
          'Microsoft.Compute/virtualMachines/runCommands/read'
          'Microsoft.Compute/virtualMachines/runCommands/write'
          'Microsoft.Compute/virtualMachines/runCommands/delete'
        ]
        notActions: []
      }
    ]
    assignableScopes: [
      resourceGroup().id
    ]
  }
}

resource githubExecutaNaVm 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vm.id, identidadeDeDeploy.id, papelDeDeploy.id)
  scope: vm
  properties: {
    description: 'O GitHub Actions executa o script de deploy na VM, e só nela.'
    roleDefinitionId: papelDeDeploy.id
    principalId: identidadeDeDeploy.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── saídas ───────────────────────────────────────────────────────────────────────────────────
// Nenhuma é segredo: são nomes e identificadores, usados no workflow e nos scripts.

@description('O endereço do site.')
output dominio string = ipPublico.properties.dnsSettings.fqdn

output ipDoSite string = ipPublico.properties.ipAddress
output nomeDaVm string = vm.name
output nomeDoCofre string = cofre.name
output contaDeArmazenamento string = armazenamento.name
output containerDeBackups string = containerDeBackups.name

@description('Para as variáveis do GitHub (AZURE_CLIENT_ID, AZURE_TENANT_ID e AZURE_SUBSCRIPTION_ID).')
output idDoClienteDeDeploy string = identidadeDeDeploy.properties.clientId
output idDoTenant string = subscription().tenantId
output idDaAssinatura string = subscription().subscriptionId
