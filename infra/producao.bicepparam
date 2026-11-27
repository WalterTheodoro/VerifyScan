// Parâmetros de produção do main.bicep (ADR-0029). Nada aqui é segredo.
//
// O id de quem preenche os segredos não fica escrito aqui: vem da variável de ambiente
// ID_DO_OPERADOR, definida por quem aplica, logo antes do comando:
//
//   $env:ID_DO_OPERADOR = az ad signed-in-user show --query id -o tsv

using './main.bicep'

param idDoOperador = readEnvironmentVariable('ID_DO_OPERADOR')

param tamanhoDaVm = 'Standard_B2als_v2'

// O site fica em verifyscan.chilecentral.cloudapp.azure.com.
param rotuloDns = 'verifyscan'

param repositorioGithub = 'WalterTheodoro/VerifyScan'
param ambienteGithub = 'producao'

// A parte pública do par gerado no provisionamento. A privada foi apagada na hora: ninguém entra
// por SSH, e a porta 22 nem está aberta. Fica versionada porque o Azure exige o mesmo valor toda
// vez que o arquivo é reaplicado.
param chaveSshPublica = 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDcZ110CTWXSTO5G6U/cuccERgM+yaBYAM8RVbFzJkTvU0qwXgs5ok7AQX8rlSl9SS+eQIvdJUkGewMibxs4cumLJWQTAbR3a5ta/qmP5i7EqnYJToWU1k0WcbpCcp9O8ukCvJ5ZGfWK3yCCU5zPJTec6DaM8ZTSx2Hsu23acjBo6N68aeJA5mS0oKtMzKje9hdhA8zdovXmw41249WiZNccCkxMeLIN7EiTcftSDJbkpdXeEXpdpeAlZ60UxuRqVgyKVNW1UqAXTwIYUpoNcaYUnFwQW+nJjj0vwBawEdyVhCMUpRc0Nu+m1qJ5TPEJpWP3ze8eYIdO3W3B88u9W07tgdAJlVuk7IbgU0R4LYYbfekQzQsp2gDDGFB7dXsixb50WPAuoUVeXRX55SDW6P2lPbF9sK0HcDw8UpjRPiDOTfyoAWxsnT+Sdv1XAdbMnIqSWxoSvydinUvj6/8anYsNm8Mh5bbNw1GEUOijRdPQ+tLBN7iTKIOMpb1frobUwdFvmFI6VI97W/OZV6sp0l6Onflrfm6vVukqc3PhOxH2yKdF81TkRP+wI+I5dgb3938X468ayEMhRO+WB5wgWw5q476M/qFm65RdNGWszhGJ26DGd3cR/EKvoXemhOLm/N5GDqwdurHTHcByZPSMpuYyxz4UYcNIVmx6RW/qlxTwQ== verifyscan-chave-descartada'
