// LevelBlue Lake Hunt: Azure Container Apps deployment.
// Creates: user-assigned identity, Log Analytics workspace for the app's own logs, storage for
// the app database, Container Apps environment, the container app with Entra ID sign-in, and
// role assignments on the Sentinel workspace's resource group.
// The container registry and the Entra app registration are created by deploy.ps1 / deploy.sh.

targetScope = 'resourceGroup'

@description('Short name used for every resource, 3 to 12 lowercase letters or digits.')
@minLength(3)
@maxLength(12)
param name string = 'lakehunt'
param location string = resourceGroup().location

@description('Container image, for example myacr.azurecr.io/lakehunt:1.0.0')
param image string
@description('Name of the Azure Container Registry (in this resource group) that holds the image.')
param registryName string

@allowed(['demo', 'live'])
param mode string = 'demo'

@description('Entra ID app registration (client) ID used for sign-in and API tokens.')
param authClientId string
@secure()
@description('Client secret of that app registration (sign-in code flow).')
param authClientSecret string

@description('Sentinel workspace: subscription, resource group, name, workspace (customer) ID, region.')
param workspaceSubscriptionId string = subscription().subscriptionId
param workspaceResourceGroup string = ''
param workspaceName string = ''
param workspaceId string = ''
param workspaceLocation string = location

@description('Grant the app identity Microsoft Sentinel Contributor and Log Analytics Contributor on the workspace resource group (needed in live mode to install solutions and create tables).')
param grantWorkspaceRoles bool = true

var suffix = uniqueString(resourceGroup().id, name)
var storageName = take(toLower('${name}${suffix}'), 24)

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${name}-id'
  location: location
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: registryName
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identity.id, 'acrpull')
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${name}-applogs-${suffix}'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
  }
}

resource share 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  name: '${storage.name}/default/lakehunt-data'
  properties: { shareQuota: 5 }
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${name}-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource envStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: env
  name: 'data'
  properties: {
    azureFile: {
      accountName: storage.name
      accountKey: storage.listKeys().keys[0].value
      shareName: 'lakehunt-data'
      accessMode: 'ReadWrite'
    }
  }
  dependsOn: [share]
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8080
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        { server: registry.properties.loginServer, identity: identity.id }
      ]
      secrets: [
        { name: 'microsoft-provider-authentication-secret', value: authClientSecret }
      ]
    }
    template: {
      containers: [
        {
          name: 'lakehunt'
          image: image
          resources: { cpu: json('1.0'), memory: '2Gi' }
          env: [
            { name: 'LAKEHUNT_MODE', value: mode }
            { name: 'LAKEHUNT_AUTH', value: 'easyauth' }
            { name: 'LAKEHUNT_DATA_DIR', value: '/data' }
            { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
            { name: 'AZURE_TENANT_ID', value: tenant().tenantId }
            { name: 'LAKEHUNT_SUBSCRIPTION_ID', value: workspaceSubscriptionId }
            { name: 'LAKEHUNT_RESOURCE_GROUP', value: workspaceResourceGroup }
            { name: 'LAKEHUNT_WORKSPACE_NAME', value: workspaceName }
            { name: 'LAKEHUNT_WORKSPACE_ID', value: workspaceId }
            { name: 'LAKEHUNT_WORKSPACE_LOCATION', value: workspaceLocation }
          ]
          volumeMounts: [ { volumeName: 'data', mountPath: '/data' } ]
          probes: [
            { type: 'Liveness', httpGet: { path: '/healthz', port: 8080 }, periodSeconds: 30 }
          ]
        }
      ]
      // SQLite holds the workflow state: keep a single replica.
      scale: { minReplicas: 1, maxReplicas: 1 }
      volumes: [
        {
          name: 'data'
          storageType: 'AzureFile'
          storageName: envStorage.name
          mountOptions: 'dir_mode=0777,file_mode=0777,uid=10001,gid=10001,nobrl'
        }
      ]
    }
  }
  dependsOn: [acrPull]
}

// Entra ID sign-in (Container Apps built-in authentication). Browsers are sent to sign in;
// API and MCP callers send a bearer token for api://<client id>. App roles arrive as "roles" claims.
resource auth 'Microsoft.App/containerApps/authConfigs@2024-03-01' = {
  parent: app
  name: 'current'
  properties: {
    platform: { enabled: true }
    globalValidation: {
      unauthenticatedClientAction: 'RedirectToLoginPage'
      redirectToProvider: 'azureactivedirectory'
      excludedPaths: ['/healthz']
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: authClientId
          clientSecretSettingName: 'microsoft-provider-authentication-secret'
          openIdIssuer: '${environment().authentication.loginEndpoint}${tenant().tenantId}/v2.0'
        }
        validation: {
          allowedAudiences: ['api://${authClientId}', authClientId]
        }
      }
    }
  }
}

module workspaceRoles 'roles.bicep' = if (grantWorkspaceRoles && !empty(workspaceResourceGroup)) {
  name: 'lakehunt-workspace-roles'
  scope: resourceGroup(workspaceSubscriptionId, workspaceResourceGroup)
  params: {
    principalId: identity.properties.principalId
  }
}

output url string = 'https://${app.properties.configuration.ingress.fqdn}'
output identityPrincipalId string = identity.properties.principalId
output identityClientId string = identity.properties.clientId
