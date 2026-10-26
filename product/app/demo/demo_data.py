"""Synthetic, de-identified demo data for ten common log sources.

All names are generic (contoso.com, user01..), all IPs are from documentation ranges
(10.0.0.0/8, 192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24). Output is deterministic
for a given anchor time. A planted incident runs through every source so the hunting
screens have something to find:

  203.0.113.45 password-sprays the VPN, sshd, Entra ID, Okta and the expenses app,
  gets into Entra ID as jsmith, signs in to the AWS console as jsmith, and the firewall
  later passes a large session from jsmith's workstation to 198.51.100.7. The badge
  reader shows jsmith entering the office minutes before the "remote" sign-in.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone

USERS = [f"user{i:02d}" for i in range(1, 41)] + ["jsmith", "akumar", "mlopez", "svc_backup"]
HOSTS = [f"WS-{i:04d}" for i in range(400, 440)]
SERVERS = ["web-07", "web-08", "db-02", "jump-01"]
INTERNAL = [f"10.20.{a}.{b}" for a in (30, 31, 32) for b in range(10, 60)]
BENIGN_EXT = [f"198.51.100.{i}" for i in range(10, 60)] + [f"192.0.2.{i}" for i in range(10, 40)]
ATTACKER = "203.0.113.45"
EXFIL = "198.51.100.7"
VICTIM_WS, VICTIM_IP = "WS-0412", "10.20.30.40"
DOMAIN = "contoso.com"


def anchor_now() -> datetime:
    return datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)


def _t(base: datetime, rnd: random.Random, days: int = 7) -> datetime:
    return base - timedelta(seconds=rnd.randint(60, days * 86400), milliseconds=rnd.randint(0, 999))


def build(now: datetime | None = None, scale: int = 1) -> dict[str, list[dict]]:
    now = now or anchor_now()
    rnd = random.Random(20261018)
    inc = (now - timedelta(days=2)).replace(hour=9, minute=14, second=2, microsecond=0)  # incident start
    T = {}

    # 1 Windows SecurityEvent ------------------------------------------------
    rows = []
    for _ in range(400 * scale):
        ok = rnd.random() > 0.12
        u = rnd.choice(USERS)
        rows.append({"TimeGenerated": _t(now, rnd), "Computer": rnd.choice(["DC01", "DC02"]) + ".corp." + DOMAIN,
                     "EventID": 4624 if ok else 4625, "TargetUserName": u, "TargetDomainName": "CONTOSO",
                     "IpAddress": rnd.choice(INTERNAL), "WorkstationName": rnd.choice(HOSTS),
                     "LogonType": rnd.choice([2, 3, 10]), "SubStatus": "0x0" if ok else "0xc000006a"})
    rows.append({"TimeGenerated": inc, "Computer": "DC01.corp." + DOMAIN, "EventID": 4625, "TargetUserName": "jsmith",
                 "TargetDomainName": "CONTOSO", "IpAddress": ATTACKER, "WorkstationName": "-", "LogonType": 3,
                 "SubStatus": "0xc000006a"})
    rows.append({"TimeGenerated": inc + timedelta(minutes=17, seconds=38), "Computer": "DC01.corp." + DOMAIN,
                 "EventID": 4624, "TargetUserName": "jsmith", "TargetDomainName": "CONTOSO", "IpAddress": VICTIM_IP,
                 "WorkstationName": VICTIM_WS, "LogonType": 2, "SubStatus": "0x0"})
    T["SecurityEvent"] = rows

    # 2 Entra ID SigninLogs --------------------------------------------------
    rows = []
    for _ in range(350 * scale):
        ok = rnd.random() > 0.1
        u = rnd.choice(USERS)
        rows.append({"TimeGenerated": _t(now, rnd), "UserPrincipalName": f"{u}@{DOMAIN}", "IPAddress":
                     rnd.choice(INTERNAL + BENIGN_EXT), "AppDisplayName": rnd.choice(["Office 365", "Azure Portal", "Teams"]),
                     "ResultType": "0" if ok else rnd.choice(["50126", "50053"]), "ClientAppUsed": "Browser",
                     "Id": f"e{rnd.getrandbits(48):012x}", "Location": "CA"})
    for i, u in enumerate(["user03", "user11", "akumar", "mlopez", "jsmith"]):
        rows.append({"TimeGenerated": inc + timedelta(seconds=20 + 9 * i), "UserPrincipalName": f"{u}@{DOMAIN}",
                     "IPAddress": ATTACKER, "AppDisplayName": "Office 365", "ResultType": "50126",
                     "ClientAppUsed": "Browser", "Id": f"spray{i}", "Location": "XX"})
    rows.append({"TimeGenerated": inc + timedelta(minutes=6, seconds=4), "UserPrincipalName": f"jsmith@{DOMAIN}",
                 "IPAddress": ATTACKER, "AppDisplayName": "Azure Portal", "ResultType": "0",
                 "ClientAppUsed": "Browser", "Id": "spray-win", "Location": "XX"})
    T["SigninLogs"] = rows

    # 3 + 4 CommonSecurityLog: FortiGate and Palo Alto ------------------------
    rows = []
    for _ in range(450 * scale):
        fg = rnd.random() > 0.45
        act = rnd.choice(["accept", "accept", "accept", "deny"]) if fg else rnd.choice(["allow", "allow", "deny"])
        rows.append({"TimeGenerated": _t(now, rnd), "DeviceVendor": "Fortinet" if fg else "Palo Alto Networks",
                     "DeviceProduct": "Fortigate" if fg else "PAN-OS", "DeviceName": "FGT-EDGE01" if fg else "PA-DC01",
                     "SourceIP": rnd.choice(INTERNAL), "DestinationIP": rnd.choice(BENIGN_EXT),
                     "SourcePort": rnd.randint(40000, 65000), "DestinationPort": rnd.choice([443, 443, 80, 53, 22]),
                     "SourceUserName": rnd.choice(USERS) if rnd.random() > 0.5 else "", "DeviceAction": act,
                     "Protocol": "TCP", "SentBytes": rnd.randint(200, 90000)})
    rows.append({"TimeGenerated": inc - timedelta(seconds=7), "DeviceVendor": "Fortinet", "DeviceProduct": "Fortigate",
                 "DeviceName": "FGT-EDGE01", "SourceIP": ATTACKER, "DestinationIP": "10.1.2.3", "SourcePort": 51544,
                 "DestinationPort": 3389, "SourceUserName": "", "DeviceAction": "deny", "Protocol": "TCP", "SentBytes": 60})
    rows.append({"TimeGenerated": inc + timedelta(seconds=40), "DeviceVendor": "Palo Alto Networks", "DeviceProduct": "PAN-OS",
                 "DeviceName": "PA-DC01", "SourceIP": ATTACKER, "DestinationIP": "10.1.2.9", "SourcePort": 51602,
                 "DestinationPort": 22, "SourceUserName": "", "DeviceAction": "deny", "Protocol": "TCP", "SentBytes": 60})
    rows.append({"TimeGenerated": inc + timedelta(hours=1, minutes=3), "DeviceVendor": "Fortinet", "DeviceProduct": "Fortigate",
                 "DeviceName": "FGT-EDGE01", "SourceIP": VICTIM_IP, "DestinationIP": EXFIL, "SourcePort": 50211,
                 "DestinationPort": 443, "SourceUserName": "jsmith", "DeviceAction": "accept", "Protocol": "TCP",
                 "SentBytes": 734003200})
    T["CommonSecurityLog"] = rows

    # 5 Linux sshd via Syslog ------------------------------------------------
    rows = []
    for _ in range(300 * scale):
        r = rnd.random()
        host, ip, u = rnd.choice(SERVERS), rnd.choice(INTERNAL), rnd.choice(["deploy", "admin", "ops"] + USERS[:5])
        if r < 0.5:
            msg = f"Accepted publickey for {u} from {ip} port {rnd.randint(30000, 60000)} ssh2"
        elif r < 0.7:
            msg = f"Failed password for {u} from {ip} port {rnd.randint(30000, 60000)} ssh2"
        elif r < 0.85:
            msg = f"pam_unix(sshd:session): session opened for user {u} by (uid=0)"
        else:
            msg = f"Received disconnect from {ip} port {rnd.randint(30000, 60000)}:11: disconnected by user"
        rows.append({"TimeGenerated": _t(now, rnd), "Computer": host, "HostIP": "10.1.2.9", "ProcessName": "sshd",
                     "Facility": "auth", "SeverityLevel": "info", "SyslogMessage": msg})
    for i, u in enumerate(["admin", "jsmith", "root", "deploy"]):
        rows.append({"TimeGenerated": inc + timedelta(seconds=28 + 11 * i), "Computer": "web-07", "HostIP": "10.1.2.9",
                     "ProcessName": "sshd", "Facility": "auth", "SeverityLevel": "info",
                     "SyslogMessage": f"Failed password for {'invalid user ' if u in ('admin', 'root') else ''}{u} from {ATTACKER} port {52114 + i} ssh2"})
    for _ in range(60 * scale):  # other daemons share the Syslog table
        rows.append({"TimeGenerated": _t(now, rnd), "Computer": rnd.choice(SERVERS), "HostIP": "10.1.2.9",
                     "ProcessName": rnd.choice(["CRON", "systemd"]), "Facility": "daemon", "SeverityLevel": "info",
                     "SyslogMessage": rnd.choice(["(root) CMD (run-parts /etc/cron.hourly)", "Started Session 42 of user root."])})
    T["Syslog"] = rows

    # 6 AWS CloudTrail -------------------------------------------------------
    rows = []
    for _ in range(250 * scale):
        login = rnd.random() < 0.3
        u = rnd.choice(USERS[:15])
        rows.append({"TimeGenerated": _t(now, rnd), "EventName": "ConsoleLogin" if login else rnd.choice(
                     ["DescribeInstances", "GetObject", "ListBuckets", "AssumeRole"]), "EventSource":
                     "signin.amazonaws.com" if login else "ec2.amazonaws.com", "SourceIpAddress": rnd.choice(BENIGN_EXT),
                     "UserIdentityUserName": u, "UserIdentityType": "IAMUser", "AWSRegion": "us-east-1",
                     "ResponseElements": json.dumps({"ConsoleLogin": "Success" if rnd.random() > 0.1 else "Failure"}) if login else "",
                     "AwsEventId": f"{rnd.getrandbits(64):016x}"})
    rows.append({"TimeGenerated": inc + timedelta(minutes=21), "EventName": "ConsoleLogin", "EventSource": "signin.amazonaws.com",
                 "SourceIpAddress": ATTACKER, "UserIdentityUserName": "jsmith", "UserIdentityType": "IAMUser",
                 "AWSRegion": "us-east-1", "ResponseElements": json.dumps({"ConsoleLogin": "Success"}), "AwsEventId": "attack-ct-1"})
    rows.append({"TimeGenerated": inc + timedelta(minutes=24), "EventName": "ListBuckets", "EventSource": "s3.amazonaws.com",
                 "SourceIpAddress": ATTACKER, "UserIdentityUserName": "jsmith", "UserIdentityType": "IAMUser",
                 "AWSRegion": "us-east-1", "ResponseElements": "", "AwsEventId": "attack-ct-2"})
    T["AWSCloudTrail"] = rows

    # 7 Okta (CCF table OktaV2_CL) -----------------------------------------------
    rows = []
    for _ in range(200 * scale):
        ok = rnd.random() > 0.15
        u = rnd.choice(USERS)
        rows.append({"TimeGenerated": _t(now, rnd), "ActorAlternateId": f"{u}@{DOMAIN}", "SrcIpAddr": rnd.choice(BENIGN_EXT),
                     "EventOriginalType": "user.session.start", "OriginalOutcomeResult": "SUCCESS" if ok else "FAILURE",
                     "EventOriginalUid": f"okta-{rnd.getrandbits(40):010x}", "HttpUserAgent": "Mozilla/5.0"})
    rows.append({"TimeGenerated": inc + timedelta(seconds=52), "ActorAlternateId": f"jsmith@{DOMAIN}", "SrcIpAddr": ATTACKER,
                 "EventOriginalType": "user.session.start", "OriginalOutcomeResult": "FAILURE",
                 "EventOriginalUid": "okta-attack-1", "HttpUserAgent": "python-requests/2.31"})
    T["OktaV2_CL"] = rows

    # 8 In-house expenses app, JSON audit log ---------------------------------------
    rows = []
    for i in range(180 * scale):
        u = rnd.choice(USERS)
        op = rnd.choice(["Login", "Login", "SubmitClaim", "ApproveClaim", "Logout"])
        rows.append({"TimeGenerated": _t(now, rnd), "Properties": json.dumps({
            "eventId": f"a-{10000 + i}", "operation": op, "outcome": "success" if rnd.random() > 0.08 else "FAILED",
            "client": {"addr": rnd.choice(INTERNAL) + (":8443" if rnd.random() > 0.7 else "")},
            "actor": {"upn": f"{u}@{DOMAIN}"}, "resource": {"url": f"https://expenses.{DOMAIN}/{op.lower()}"}})})
    rows.append({"TimeGenerated": inc + timedelta(minutes=1, seconds=1), "Properties": json.dumps({
        "eventId": "a-attack-1", "operation": "Login", "outcome": "FAILED", "client": {"addr": ATTACKER + ":8443"},
        "actor": {"upn": f"JSmith@{DOMAIN}"}, "resource": {"url": f"https://expenses.{DOMAIN}/login"}})})
    T["AppAudit_CL"] = rows

    # 9 VPN appliance, raw key=value text ----------------------------------------
    rows = []
    for _ in range(220 * scale):
        ok = rnd.random() > 0.15
        u = rnd.choice(USERS)
        txt = (f"vpn01 auth={'ok' if ok else 'fail'} user={u} src={rnd.choice(BENIGN_EXT)} "
               + (f"tunnel=ipsec-{rnd.randint(1, 40)}" if ok else "tunnel=none reason=bad-otp"))
        rows.append({"TimeGenerated": _t(now, rnd), "RawData": txt})
    for _ in range(40 * scale):
        rows.append({"TimeGenerated": _t(now, rnd), "RawData": f"vpn01 keepalive peers={rnd.randint(10, 90)} load={rnd.randint(1, 99)}"})
    rows.append({"TimeGenerated": inc + timedelta(minutes=1, seconds=18), "RawData":
                 f"vpn01 auth=fail user=jsmith src={ATTACKER} tunnel=none reason=bad-otp"})
    T["VpnAppliance_CL"] = rows

    # 10 Badge reader: NEW source, nobody has reviewed it yet ---------------------
    rows = []
    for _ in range(160 * scale):
        u = rnd.choice(USERS)
        rows.append({"TimeGenerated": _t(now, rnd), "RawData":
                     f"BADGE door=HQ-{rnd.choice(['MAIN', 'LAB', 'DOCK'])} badge={rnd.randint(10000, 99999)} "
                     f"holder={u}@{DOMAIN} result={'granted' if rnd.random() > 0.05 else 'denied'} reader=10.40.0.{rnd.randint(2, 20)}"})
    rows.append({"TimeGenerated": inc - timedelta(minutes=19), "RawData":
                 f"BADGE door=HQ-MAIN badge=41207 holder=jsmith@{DOMAIN} result=granted reader=10.40.0.3"})
    T["BadgeReader_CL"] = rows
    return T


SCENARIO = {
    "attacker_ip": ATTACKER, "victim_user": "jsmith", "victim_host": VICTIM_WS, "victim_ip": VICTIM_IP,
    "exfil_ip": EXFIL,
    "story": "Password spray from 203.0.113.45 across VPN, sshd, Entra ID, Okta and the expenses app; "
             "Entra ID success for jsmith; AWS console sign-in as jsmith from the same IP; large outbound "
             "session from jsmith's workstation to 198.51.100.7. The badge reader (not yet reviewed) puts "
             "jsmith in the office at the time.",
}
