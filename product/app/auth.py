"""Caller identity and role checks.

In Azure the app runs behind Container Apps built-in authentication (Entra ID). The platform
validates the sign-in or bearer token and passes the caller in X-MS-CLIENT-PRINCIPAL
(base64 JSON). App roles come through as "roles" claims:
  LakeHunt.Admin    approve tenant changes, approve registry entries, settings
  LakeHunt.Analyst  review fields, edit draft registry entries, run validation, hunt
  LakeHunt.Viewer   read dashboards and hunt
The app trusts that header only when LAKEHUNT_AUTH=easyauth, where ingress is restricted
to the platform's authentication proxy.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request

from app.config import settings

RANK = {"viewer": 1, "analyst": 2, "admin": 3}


@dataclass
class User:
    name: str
    oid: str
    roles: list[str]

    @property
    def level(self) -> int:
        lv = 0
        if settings.role_viewer in self.roles:
            lv = 1
        if settings.role_analyst in self.roles:
            lv = 2
        if settings.role_admin in self.roles:
            lv = 3
        return lv

    @property
    def role(self) -> str:
        return {0: "none", 1: "viewer", 2: "analyst", 3: "admin"}[self.level]


def current_user(request: Request) -> User:
    if settings.auth_mode != "easyauth":
        demo_role = request.headers.get("X-LakeHunt-Demo-Role", "admin").lower()
        roles = {"admin": [settings.role_admin], "analyst": [settings.role_analyst],
                 "viewer": [settings.role_viewer]}.get(demo_role, [settings.role_admin])
        return User(name="demo.user@contoso.com", oid="00000000-0000-0000-0000-000000000000", roles=roles)
    raw = request.headers.get("X-MS-CLIENT-PRINCIPAL")
    if not raw:
        raise HTTPException(401, "Not signed in")
    try:
        p = json.loads(base64.b64decode(raw))
    except Exception:
        raise HTTPException(401, "Bad principal header")
    claims = p.get("claims", [])
    get = lambda *t: next((c["val"] for c in claims if c.get("typ") in t), "")  # noqa: E731
    roles = [c["val"] for c in claims if c.get("typ") in ("roles", p.get("role_typ", "roles"),
                                                           "http://schemas.microsoft.com/ws/2008/06/identity/claims/role")]
    name = get("name", "preferred_username", "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn") or \
        request.headers.get("X-MS-CLIENT-PRINCIPAL-NAME", "unknown")
    oid = get("http://schemas.microsoft.com/identity/claims/objectidentifier", "oid")
    return User(name=name, oid=oid, roles=roles)


def require(role: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.level < RANK[role]:
            raise HTTPException(403, f"Requires the {role} role")
        return user
    return dep
