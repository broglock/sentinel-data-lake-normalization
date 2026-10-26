// Role assignments for the Lake Hunt identity on the Sentinel workspace's resource group.
//   Microsoft Sentinel Contributor: Content hub catalog and solution installs
//   Log Analytics Contributor:      tables API (create tables, set plan and retention), ARM template deployments
// Querying the data lake also needs the identity added to a Sentinel data lake reader role in
// Microsoft Defender XDR unified RBAC; see the README (manual step).
targetScope = 'resourceGroup'

param principalId string

var roles = {
  sentinelContributor: 'ab8e14d6-4a74-4a29-9ba8-549422addade'
  logAnalyticsContributor: '92aaf0da-9dab-42b6-94a3-d43ce8d16293'
}

resource assignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for r in items(roles): {
  name: guid(resourceGroup().id, principalId, r.value)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', r.value)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}]
