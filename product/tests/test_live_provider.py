"""Live provider against a mocked Azure: checks the exact requests the app sends (no tenant needed)."""
from __future__ import annotations

import json

import httpx
import pytest

from app.config import settings
from app.providers import azure as az


class FakeCred:
    def get_token(self, scope):
        class T:
            token = "tok-" + scope
            expires_on = 4102444800
        return T()


@pytest.fixture()
def prov(monkeypatch):
    for k, v in dict(subscription_id="sub1", resource_group="rg-sent", workspace_name="law1",
                     workspace_id="11111111-2222-3333-4444-555555555555", workspace_location="canadacentral").items():
        monkeypatch.setattr(settings, k, v)
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        u = str(req.url)
        if "contentProductPackages" in u and "pkg-okta" not in req.url.path and req.method == "GET":
            return httpx.Response(200, json={"value": [{"name": "pkg-okta", "properties": {"displayName": "Okta Single Sign-On", "contentKind": "Solution"}}]})
        if "contentProductPackages/pkg-okta" in u:
            return httpx.Response(200, json={"name": "pkg-okta", "properties": {"displayName": "Okta Single Sign-On", "version": "3.1.0",
                                                                               "contentId": "azuresentinel.okta", "packagedContent": {"resources": []}}})
        if "/deployments/" in u:
            return httpx.Response(201, json={"properties": {"provisioningState": "Accepted"}})
        if "/tables/" in u and req.method == "PUT":
            return httpx.Response(200, json={"properties": {"provisioningState": "Succeeded"}})
        if u.startswith(settings.lake_query_url):
            return httpx.Response(200, json=[{"FrameType": "DataSetHeader"}, {"FrameType": "DataTable", "TableKind": "PrimaryResult",
                                                                              "Columns": [{"ColumnName": "SourceGroup"}, {"ColumnName": "Events"}],
                                                                              "Rows": [["Syslog:sshd", 4]]}])
        return httpx.Response(404, text="unexpected " + u)

    p = az.AzureProvider.__new__(az.AzureProvider)
    p.cred, p._tok = FakeCred(), {}
    p.http = httpx.Client(transport=httpx.MockTransport(handler))
    return p, calls


def test_create_table_sends_plan_retention_and_schema(prov):
    p, calls = prov
    r = p.create_table("OktaV2_CL", [{"name": "ActorAlternateId", "type": "string"}], "Auxiliary", 365)
    assert r["provisioningState"] == "Succeeded"
    req = calls[-1]
    assert req.method == "PUT" and req.url.path.endswith("/workspaces/law1/tables/OktaV2_CL")
    assert req.url.params["api-version"] == settings.tables_api_version
    body = json.loads(req.content)["properties"]
    assert body["plan"] == "Auxiliary" and body["totalRetentionInDays"] == 365
    assert body["schema"]["columns"][0] == {"name": "TimeGenerated", "type": "datetime"}
    assert req.headers["Authorization"] == "Bearer tok-https://management.azure.com/.default"


def test_install_solution_deploys_packaged_content(prov):
    p, calls = prov
    r = p.install_solution({"name": "Okta Single Sign-On"})
    assert r["provisioningState"] == "Accepted" and r["version"] == "3.1.0"
    dep = calls[-1]
    assert dep.method == "PUT" and "/providers/Microsoft.Resources/deployments/" in dep.url.path
    body = json.loads(dep.content)["properties"]
    assert body["mode"] == "Incremental" and body["parameters"]["workspace"]["value"] == "law1"


def test_hunt_escapes_values_and_parses_v2_frames(prov):
    p, calls = prov
    rows = p.hunt("hunt_value", value='CONTOSO\\j"smith', days=7)
    assert rows == [{"SourceGroup": "Syslog:sshd", "Events": 4}]
    sent = json.loads(calls[-1].content)
    assert sent["db"] == "law1-11111111-2222-3333-4444-555555555555"
    assert 'CONTOSO\\\\j\\"smith' in sent["csl"] and "{Value}" not in sent["csl"]
    with pytest.raises(ValueError):
        p.hunt("hunt_entity", entity_type="ip); drop", value="x")
    with pytest.raises(ValueError):
        p.hunt("search_raw", table="Syslog | take 1", text="x")


def test_parse_kusto_v1_and_la():
    assert az.parse_kusto({"tables": [{"columns": [{"name": "a"}], "rows": [[1]]}]}) == [{"a": 1}]
    assert az.parse_kusto({"Tables": [{"Columns": [{"ColumnName": "b"}], "Rows": [[2]]}]}) == [{"b": 2}]
