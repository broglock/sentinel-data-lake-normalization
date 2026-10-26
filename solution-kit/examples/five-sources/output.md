# Five sources: actual output of the demo run

Rows indexed per group: {'SecurityEvent:Logon': 9, 'CEF:Fortinet/Fortigate': 7, 'Syslog:sshd': 9, 'AppAudit_CL:v2': 6, 'VpnAppliance_CL:raw': 2}

## SecurityEvent:Logon

| Time | EntityType | Role | Value | ValueNorm | ValueType | EventType | EventResult | MappingLayer | MappingTier |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 09:14:02 | host | Dvc | DC01.corp.contoso.com | dc01 | FQDN | Logon | Failure | registry | 1 |
| 09:14:02 | ip | Src | 203.0.113.45 | 203.0.113.45 | IPv4 | Logon | Failure | registry | 1 |
| 09:14:02 | user | Target | jsmith | jsmith | Simple | Logon | Failure | registry | 1 |
| 09:31:40 | host | Src | WS-0412 | ws-0412 | Hostname | Logon | Success | registry | 1 |
| 09:31:40 | host | Dvc | DC01.corp.contoso.com | dc01 | FQDN | Logon | Success | registry | 1 |
| 09:31:40 | ip | Src | 10.20.30.40 | 10.20.30.40 | IPv4 | Logon | Success | registry | 1 |
| 09:31:40 | user | Target | jsmith | jsmith | Simple | Logon | Success | registry | 1 |
| 09:32:05 | host | Dvc | DC01.corp.contoso.com | dc01 | FQDN | Logon | Success | registry | 1 |
| 09:32:05 | user | Target | svc_backup | svc_backup | Simple | Logon | Success | registry | 1 |

## CEF:Fortinet/Fortigate

| Time | EntityType | Role | Value | ValueNorm | ValueType | EventType | EventResult | MappingLayer | MappingTier |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 09:13:55 | host | Dvc | FGT-EDGE01 | fgt-edge01 | Hostname | NetworkSession | Failure | registry | 1 |
| 09:13:55 | ip | Src | 203.0.113.45 | 203.0.113.45 | IPv4 | NetworkSession | Failure | registry | 1 |
| 09:13:55 | ip | Dst | 10.1.2.3 | 10.1.2.3 | IPv4 | NetworkSession | Failure | registry | 1 |
| 09:31:12 | host | Dvc | FGT-EDGE01 | fgt-edge01 | Hostname | NetworkSession | Success | registry | 1 |
| 09:31:12 | ip | Src | 10.20.30.40 | 10.20.30.40 | IPv4 | NetworkSession | Success | registry | 1 |
| 09:31:12 | ip | Dst | 198.51.100.7 | 198.51.100.7 | IPv4 | NetworkSession | Success | registry | 1 |
| 09:31:12 | user | Src | jsmith | jsmith | Simple | NetworkSession | Success | registry | 1 |

## Syslog:sshd

| Time | EntityType | Role | Value | ValueNorm | ValueType | EventType | EventResult | MappingLayer | MappingTier |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 09:14:30 | host | Dvc | web-07 | web-07 | Hostname | Logon | Failure | template | 1 |
| 09:14:30 | ip | Src | 203.0.113.45 | 203.0.113.45 | IPv4 | Logon | Failure | template | 1 |
| 09:14:30 | user | Target | admin | admin | Simple | Logon | Failure | template | 1 |
| 09:14:41 | host | Dvc | web-07 | web-07 | Hostname | Logon | Failure | template | 1 |
| 09:14:41 | ip | Src | 203.0.113.45 | 203.0.113.45 | IPv4 | Logon | Failure | template | 1 |
| 09:14:41 | user | Target | jsmith | jsmith | Simple | Logon | Failure | template | 1 |
| 09:35:00 | host | Dvc | web-07 | web-07 | Hostname | Logon | Success | template | 1 |
| 09:35:00 | ip | Src | 10.20.30.40 | 10.20.30.40 | IPv4 | Logon | Success | template | 1 |
| 09:35:00 | user | Target | deploy | deploy | Simple | Logon | Success | template | 1 |

## AppAudit_CL:v2

| Time | EntityType | Role | Value | ValueNorm | ValueType | EventType | EventResult | MappingLayer | MappingTier |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 09:15:03 | ip | Src | 203.0.113.45:8443 | 203.0.113.45 | IPv4 | Logon | Failure | registry | 1 |
| 09:15:03 | url | Unknown | https://expenses.contoso.com/login | https://expenses.contoso.com/login | URL | Logon | Failure | registry | 1 |
| 09:15:03 | user | Target | JSmith@contoso.com | jsmith | UPN | Logon | Failure | registry | 1 |
| 09:33:09 | ip | Src | 10.20.30.40 | 10.20.30.40 | IPv4 | Logon | Success | registry | 1 |
| 09:33:09 | url | Unknown | https://expenses.contoso.com/login | https://expenses.contoso.com/login | URL | Logon | Success | registry | 1 |
| 09:33:09 | user | Target | jsmith@contoso.com | jsmith | UPN | Logon | Success | registry | 1 |

## VpnAppliance_CL:raw

| Time | EntityType | Role | Value | ValueNorm | ValueType | EventType | EventResult | MappingLayer | MappingTier |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 09:15:20 | ip | Unknown | 203.0.113.45 | 203.0.113.45 | IPv4 |  |  | classifier | 2 |
| 09:33:50 | ip | Unknown | 10.20.30.40 | 10.20.30.40 | IPv4 |  |  | classifier | 2 |

## HuntEvent rows (Tier 1, structured sources)

| Time | SourceGroup | EventType | EventResult | SrcIpAddr | DstIpAddr | DstPortNumber | TargetUsername | SrcUsername | DvcHostname | DvcAction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 09:13:55 | CEF:Fortinet/Fortigate | NetworkSession | Failure | 203.0.113.45 | 10.1.2.3 | 3389 |  |  | FGT-EDGE01 | deny |
| 09:14:02 | SecurityEvent:Logon | Logon | Failure | 203.0.113.45 |  |  | jsmith |  | DC01.corp.contoso.com |  |
| 09:15:03 | AppAudit_CL:v2 | Logon | Failure | 203.0.113.45 |  |  | JSmith@contoso.com |  |  |  |
| 09:31:12 | CEF:Fortinet/Fortigate | NetworkSession | Success | 10.20.30.40 | 198.51.100.7 | 443 |  | jsmith | FGT-EDGE01 | accept |
| 09:31:40 | SecurityEvent:Logon | Logon | Success | 10.20.30.40 |  |  | jsmith |  | DC01.corp.contoso.com |  |
| 09:32:05 | SecurityEvent:Logon | Logon | Success |  |  |  | svc_backup |  | DC01.corp.contoso.com |  |
| 09:33:09 | AppAudit_CL:v2 | Logon | Success | 10.20.30.40 |  |  | jsmith@contoso.com |  |  |  |

## hunt_value('203.0.113.45')

| SourceTable | SourceGroup | EntityType | Events | Roles | Tiers | Results |
| --- | --- | --- | --- | --- | --- | --- |
| AppAudit_CL | AppAudit_CL:v2 | ip | 1 | Src | 1 | Failure |
| CommonSecurityLog | CEF:Fortinet/Fortigate | ip | 1 | Src | 1 | Failure |
| SecurityEvent | SecurityEvent:Logon | ip | 1 | Src | 1 | Failure |
| Syslog | Syslog:sshd | ip | 2 | Src | 1 | Failure |
| VpnAppliance_CL | VpnAppliance_CL:raw | ip | 1 | Unknown | 2 |  |

## auth_events('CONTOSO\\jsmith')

| Time | SourceGroup | EventType | EventResult | User | SrcIpAddr |
| --- | --- | --- | --- | --- | --- |
| 09:14:02 | SecurityEvent:Logon | Logon | Failure | jsmith | 203.0.113.45 |
| 09:14:41 | Syslog:sshd | Logon | Failure | jsmith | 203.0.113.45 |
| 09:15:03 | AppAudit_CL:v2 | Logon | Failure | JSmith@contoso.com | 203.0.113.45 |
| 09:31:40 | SecurityEvent:Logon | Logon | Success | jsmith | 10.20.30.40 |
| 09:33:09 | AppAudit_CL:v2 | Logon | Success | jsmith@contoso.com | 10.20.30.40 |

# After review: VPN appliance templates approved

## VpnAppliance_CL:raw (now Tier 1)

| Time | EntityType | Role | Value | ValueNorm | ValueType | EventType | EventResult | MappingLayer | MappingTier |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 09:15:20 | ip | Src | 203.0.113.45 | 203.0.113.45 | IPv4 | Logon | Failure | template | 1 |
| 09:15:20 | user | Target | jsmith | jsmith | Simple | Logon | Failure | template | 1 |
| 09:33:50 | ip | Src | 10.20.30.40 | 10.20.30.40 | IPv4 | Logon | Success | template | 1 |
| 09:33:50 | user | Target | jsmith | jsmith | Simple | Logon | Success | template | 1 |

## hunt_value('203.0.113.45') after review

| SourceTable | SourceGroup | EntityType | Events | Roles | Tiers | Results |
| --- | --- | --- | --- | --- | --- | --- |
| AppAudit_CL | AppAudit_CL:v2 | ip | 1 | Src | 1 | Failure |
| CommonSecurityLog | CEF:Fortinet/Fortigate | ip | 1 | Src | 1 | Failure |
| SecurityEvent | SecurityEvent:Logon | ip | 1 | Src | 1 | Failure |
| Syslog | Syslog:sshd | ip | 2 | Src | 1 | Failure |
| VpnAppliance_CL | VpnAppliance_CL:raw | ip | 1 | Src | 1 | Failure |

## auth_events('CONTOSO\\jsmith') after review

| Time | SourceGroup | EventType | EventResult | User | SrcIpAddr |
| --- | --- | --- | --- | --- | --- |
| 09:14:02 | SecurityEvent:Logon | Logon | Failure | jsmith | 203.0.113.45 |
| 09:14:41 | Syslog:sshd | Logon | Failure | jsmith | 203.0.113.45 |
| 09:15:03 | AppAudit_CL:v2 | Logon | Failure | JSmith@contoso.com | 203.0.113.45 |
| 09:15:20 | VpnAppliance_CL:raw | Logon | Failure | jsmith | 203.0.113.45 |
| 09:31:40 | SecurityEvent:Logon | Logon | Success | jsmith | 10.20.30.40 |
| 09:33:09 | AppAudit_CL:v2 | Logon | Success | jsmith@contoso.com | 10.20.30.40 |
| 09:33:50 | VpnAppliance_CL:raw | Logon | Success | jsmith | 10.20.30.40 |
