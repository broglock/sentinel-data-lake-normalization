# Five sources: actual output of the demo run

Rows indexed per group: {'SecurityEvent:Logon': 10, 'CEF:Fortinet/Fortigate': 9, 'Syslog:sshd': 10, 'AppAudit_CL:v2': 8, 'VpnAppliance_CL:raw': 4}

HuntEntity is an hourly rollup: one row per hour, group, entity, role and result, with Count, FirstSeen, LastSeen and up to three sample record keys for the pivot to raw rows.

## SecurityEvent:Logon

| Hour | EntityType | Role | Value | ValueNorm | ValueType | EventType | EventResult | MappingLayer | MappingTier | Count | FirstSeen |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 09:00 | host | Dvc | DC01.corp.contoso.com | dc01 | FQDN | Logon | Failure | registry | 1 | 1 | 09:14:02 |
| 09:00 | host | Dvc | DC01.corp.contoso.com | dc01 | FQDN | Logon | Success | registry | 1 | 2 | 09:31:40 |
| 09:00 | host | Src | WS-0412 | ws-0412 | Hostname | Logon | Success | registry | 1 | 1 | 09:31:40 |
| 09:00 | ip | Src | 10.20.30.40 | 10.20.30.40 | IPv4 | Logon | Success | registry | 1 | 1 | 09:31:40 |
| 09:00 | ip | Src | 203.0.113.45 | 203.0.113.45 | IPv4 | Logon | Failure | registry | 1 | 1 | 09:14:02 |
| 09:00 | user | Target | jsmith | jsmith | Simple | Logon | Failure | registry | 1 | 1 | 09:14:02 |
| 09:00 | user | Target | jsmith | jsmith | Simple | Logon | Success | registry | 1 | 1 | 09:31:40 |
| 09:00 | user | Target | svc_backup | svc_backup | Simple | Logon | Success | registry | 1 | 1 | 09:32:05 |

## CEF:Fortinet/Fortigate

| Hour | EntityType | Role | Value | ValueNorm | ValueType | EventType | EventResult | MappingLayer | MappingTier | Count | FirstSeen |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 09:00 | host | Dvc | FGT-EDGE01 | fgt-edge01 | Hostname | NetworkSession | Failure | registry | 1 | 1 | 09:13:55 |
| 09:00 | host | Dvc | FGT-EDGE01 | fgt-edge01 | Hostname | NetworkSession | Success | registry | 1 | 1 | 09:31:12 |
| 09:00 | ip | Dst | 10.1.2.3 | 10.1.2.3 | IPv4 | NetworkSession | Failure | registry | 1 | 1 | 09:13:55 |
| 09:00 | ip | Dst | 198.51.100.7 | 198.51.100.7 | IPv4 | NetworkSession | Success | registry | 1 | 1 | 09:31:12 |
| 09:00 | ip | Src | 10.20.30.40 | 10.20.30.40 | IPv4 | NetworkSession | Success | registry | 1 | 1 | 09:31:12 |
| 09:00 | ip | Src | 203.0.113.45 | 203.0.113.45 | IPv4 | NetworkSession | Failure | registry | 1 | 1 | 09:13:55 |
| 09:00 | user | Src | jsmith | jsmith | Simple | NetworkSession | Success | registry | 1 | 1 | 09:31:12 |

## Syslog:sshd

| Hour | EntityType | Role | Value | ValueNorm | ValueType | EventType | EventResult | MappingLayer | MappingTier | Count | FirstSeen |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 09:00 | host | Dvc | web-07 | web-07 | Hostname | Logon | Failure | template | 1 | 2 | 09:14:30 |
| 09:00 | host | Dvc | web-07 | web-07 | Hostname | Logon | Success | template | 1 | 1 | 09:35:00 |
| 09:00 | ip | Src | 10.20.30.40 | 10.20.30.40 | IPv4 | Logon | Success | template | 1 | 1 | 09:35:00 |
| 09:00 | ip | Src | 203.0.113.45 | 203.0.113.45 | IPv4 | Logon | Failure | template | 1 | 2 | 09:14:30 |
| 09:00 | user | Target | admin | admin | Simple | Logon | Failure | template | 1 | 1 | 09:14:30 |
| 09:00 | user | Target | deploy | deploy | Simple | Logon | Success | template | 1 | 1 | 09:35:00 |
| 09:00 | user | Target | jsmith | jsmith | Simple | Logon | Failure | template | 1 | 1 | 09:14:41 |

## AppAudit_CL:v2

| Hour | EntityType | Role | Value | ValueNorm | ValueType | EventType | EventResult | MappingLayer | MappingTier | Count | FirstSeen |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 09:00 | ip | Src | 10.20.30.40 | 10.20.30.40 | IPv4 | Logon | Success | registry | 1 | 1 | 09:33:09 |
| 09:00 | ip | Src | 203.0.113.45:8443 | 203.0.113.45 | IPv4 | Logon | Failure | registry | 1 | 1 | 09:15:03 |
| 09:00 | url | Unknown | https://expenses.contoso.com/login | https://expenses.contoso.com/login | URL | Logon | Failure | registry | 1 | 1 | 09:15:03 |
| 09:00 | url | Unknown | https://expenses.contoso.com/login | https://expenses.contoso.com/login | URL | Logon | Success | registry | 1 | 1 | 09:33:09 |
| 09:00 | user | Target | JSmith@contoso.com | jsmith | UPN | Logon | Failure | registry | 1 | 1 | 09:15:03 |
| 09:00 | user | Target | jsmith@contoso.com | jsmith | UPN | Logon | Success | registry | 1 | 1 | 09:33:09 |

## VpnAppliance_CL:raw

| Hour | EntityType | Role | Value | ValueNorm | ValueType | EventType | EventResult | MappingLayer | MappingTier | Count | FirstSeen |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 09:00 | ip | Unknown | 10.20.30.40 | 10.20.30.40 | IPv4 |  |  | classifier | 2 | 1 | 09:33:50 |
| 09:00 | ip | Unknown | 203.0.113.45 | 203.0.113.45 | IPv4 |  |  | classifier | 2 | 1 | 09:15:20 |

## _stats rows (what notebook 03 reads for coverage)

| SourceGroup | RowsRead | RowsWithEntity | RowsTemplateMatched |
| --- | --- | --- | --- |
| AppAudit_CL:v2 | 2 | 2 |  |
| CEF:Fortinet/Fortigate | 2 | 2 |  |
| SecurityEvent:Logon | 3 | 3 |  |
| Syslog:sshd | 3 | 3 | 3 |
| VpnAppliance_CL:raw | 2 | 2 |  |

## HuntEvent rows (Tier 1 field rules and Tier 1 templates, hourly rollup)

One row per hour and unique combination of the mapped ASIM fields, with Count. Time is FirstSeen.

| Time | SourceGroup | EventType | EventResult | SrcIpAddr | DstIpAddr | DstPortNumber | TargetUsername | SrcUsername | DvcHostname | DvcAction | Count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 09:13:55 | CEF:Fortinet/Fortigate | NetworkSession | Failure | 203.0.113.45 | 10.1.2.3 | 3389 |  |  | FGT-EDGE01 | deny | 1 |
| 09:14:02 | SecurityEvent:Logon | Logon | Failure | 203.0.113.45 |  |  | jsmith |  | DC01.corp.contoso.com |  | 1 |
| 09:14:30 | Syslog:sshd | Logon | Failure | 203.0.113.45 |  |  | admin |  | web-07 |  | 1 |
| 09:14:41 | Syslog:sshd | Logon | Failure | 203.0.113.45 |  |  | jsmith |  | web-07 |  | 1 |
| 09:15:03 | AppAudit_CL:v2 | Logon | Failure | 203.0.113.45 |  |  | JSmith@contoso.com |  |  |  | 1 |
| 09:31:12 | CEF:Fortinet/Fortigate | NetworkSession | Success | 10.20.30.40 | 198.51.100.7 | 443 |  | jsmith | FGT-EDGE01 | accept | 1 |
| 09:31:40 | SecurityEvent:Logon | Logon | Success | 10.20.30.40 |  |  | jsmith |  | DC01.corp.contoso.com |  | 1 |
| 09:32:05 | SecurityEvent:Logon | Logon | Success |  |  |  | svc_backup |  | DC01.corp.contoso.com |  | 1 |
| 09:33:09 | AppAudit_CL:v2 | Logon | Success | 10.20.30.40 |  |  | jsmith@contoso.com |  |  |  | 1 |
| 09:35:00 | Syslog:sshd | Logon | Success | 10.20.30.40 |  |  | deploy |  | web-07 |  | 1 |

## hunt_value('203.0.113.45')

| SourceTable | SourceGroup | EntityType | Events | Roles | Tiers | Results |
| --- | --- | --- | --- | --- | --- | --- |
| AppAudit_CL | AppAudit_CL:v2 | ip | 1 | Src | 1 | Failure |
| CommonSecurityLog | CEF:Fortinet/Fortigate | ip | 1 | Src | 1 | Failure |
| SecurityEvent | SecurityEvent:Logon | ip | 1 | Src | 1 | Failure |
| Syslog | Syslog:sshd | ip | 2 | Src | 1 | Failure |
| VpnAppliance_CL | VpnAppliance_CL:raw | ip | 1 | Unknown | 2 |  |

## auth_events('CONTOSO\\jsmith')

| Time | SourceGroup | EventType | EventResult | User | SrcIpAddr | Count |
| --- | --- | --- | --- | --- | --- | --- |
| 09:14:02 | SecurityEvent:Logon | Logon | Failure | jsmith | 203.0.113.45 | 1 |
| 09:14:41 | Syslog:sshd | Logon | Failure | jsmith | 203.0.113.45 | 1 |
| 09:15:03 | AppAudit_CL:v2 | Logon | Failure | JSmith@contoso.com | 203.0.113.45 | 1 |
| 09:31:40 | SecurityEvent:Logon | Logon | Success | jsmith | 10.20.30.40 | 1 |
| 09:33:09 | AppAudit_CL:v2 | Logon | Success | jsmith@contoso.com | 10.20.30.40 | 1 |

# After review: VPN appliance templates approved

## VpnAppliance_CL:raw (now Tier 1)

| Hour | EntityType | Role | Value | ValueNorm | ValueType | EventType | EventResult | MappingLayer | MappingTier | Count | FirstSeen |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 09:00 | ip | Src | 10.20.30.40 | 10.20.30.40 | IPv4 | Logon | Success | template | 1 | 1 | 09:33:50 |
| 09:00 | ip | Src | 203.0.113.45 | 203.0.113.45 | IPv4 | Logon | Failure | template | 1 | 1 | 09:15:20 |
| 09:00 | user | Target | jsmith | jsmith | Simple | Logon | Failure | template | 1 | 1 | 09:15:20 |
| 09:00 | user | Target | jsmith | jsmith | Simple | Logon | Success | template | 1 | 1 | 09:33:50 |

## VpnAppliance_CL:raw _stats rows

| SourceGroup | RowsRead | RowsWithEntity | RowsTemplateMatched |
| --- | --- | --- | --- |
| VpnAppliance_CL:raw | 2 | 2 | 2 |

## hunt_value('203.0.113.45') after review

| SourceTable | SourceGroup | EntityType | Events | Roles | Tiers | Results |
| --- | --- | --- | --- | --- | --- | --- |
| AppAudit_CL | AppAudit_CL:v2 | ip | 1 | Src | 1 | Failure |
| CommonSecurityLog | CEF:Fortinet/Fortigate | ip | 1 | Src | 1 | Failure |
| SecurityEvent | SecurityEvent:Logon | ip | 1 | Src | 1 | Failure |
| Syslog | Syslog:sshd | ip | 2 | Src | 1 | Failure |
| VpnAppliance_CL | VpnAppliance_CL:raw | ip | 1 | Src | 1 | Failure |

## auth_events('CONTOSO\\jsmith') after review

| Time | SourceGroup | EventType | EventResult | User | SrcIpAddr | Count |
| --- | --- | --- | --- | --- | --- | --- |
| 09:14:02 | SecurityEvent:Logon | Logon | Failure | jsmith | 203.0.113.45 | 1 |
| 09:14:41 | Syslog:sshd | Logon | Failure | jsmith | 203.0.113.45 | 1 |
| 09:15:03 | AppAudit_CL:v2 | Logon | Failure | JSmith@contoso.com | 203.0.113.45 | 1 |
| 09:15:20 | VpnAppliance_CL:raw | Logon | Failure | jsmith | 203.0.113.45 | 1 |
| 09:31:40 | SecurityEvent:Logon | Logon | Success | jsmith | 10.20.30.40 | 1 |
| 09:33:09 | AppAudit_CL:v2 | Logon | Success | jsmith@contoso.com | 10.20.30.40 | 1 |
| 09:33:50 | VpnAppliance_CL:raw | Logon | Success | jsmith | 10.20.30.40 | 1 |
