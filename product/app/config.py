"""Settings from environment variables. Every value has a safe default for demo mode."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class Settings:
    product_name: str = "LevelBlue Lake Hunt"
    version: str = "1.0.0"
    # demo: in-memory demo data, no Azure calls. live: Azure APIs with the app's managed identity.
    mode: str = field(default_factory=lambda: _env("LAKEHUNT_MODE", "demo"))
    data_dir: Path = field(default_factory=lambda: Path(_env("LAKEHUNT_DATA_DIR", str(APP_DIR.parent / "var"))))
    # Auth: "easyauth" reads the identity Azure Container Apps authentication passes in headers.
    # "none" is for local demo only; every caller is treated as an Admin.
    auth_mode: str = field(default_factory=lambda: _env("LAKEHUNT_AUTH", "none"))
    role_admin: str = "LakeHunt.Admin"
    role_analyst: str = "LakeHunt.Analyst"
    role_viewer: str = "LakeHunt.Viewer"
    # Target workspace (live mode)
    tenant_id: str = field(default_factory=lambda: _env("AZURE_TENANT_ID"))
    subscription_id: str = field(default_factory=lambda: _env("LAKEHUNT_SUBSCRIPTION_ID"))
    resource_group: str = field(default_factory=lambda: _env("LAKEHUNT_RESOURCE_GROUP"))
    workspace_name: str = field(default_factory=lambda: _env("LAKEHUNT_WORKSPACE_NAME"))
    workspace_id: str = field(default_factory=lambda: _env("LAKEHUNT_WORKSPACE_ID"))
    workspace_location: str = field(default_factory=lambda: _env("LAKEHUNT_WORKSPACE_LOCATION"))
    # API versions and endpoints (kept configurable: several are preview surfaces)
    arm_endpoint: str = "https://management.azure.com"
    tables_api_version: str = field(default_factory=lambda: _env("LAKEHUNT_TABLES_API", "2023-01-01-preview"))
    content_api_version: str = field(default_factory=lambda: _env("LAKEHUNT_CONTENT_API", "2024-09-01"))
    deployments_api_version: str = "2021-04-01"
    lake_query_url: str = field(default_factory=lambda: _env(
        "LAKEHUNT_LAKE_QUERY_URL", "https://api.securityplatform.microsoft.com/lake/kql/v2/rest/query"))
    lake_scope: str = field(default_factory=lambda: _env(
        "LAKEHUNT_LAKE_SCOPE", "https://api.securityplatform.microsoft.com/.default"))
    la_query_url: str = "https://api.loganalytics.io/v1/workspaces/{workspace_id}/query"
    la_scope: str = "https://api.loganalytics.io/.default"
    # Index table names in the lake (notebook output tables carry the _SPRK suffix)
    entity_table: str = "HuntEntity_SPRK"
    event_table: str = "HuntEvent_SPRK"
    coverage_table: str = "HuntCoverage_SPRK"
    inventory_table: str = "FieldInventory_SPRK"
    templates_table: str = "TemplateCandidates_SPRK"
    # Thresholds used by validation and coverage status
    min_extraction: float = 0.90
    min_template_match: float = 0.70
    kql_job_limit: int = 100
    kql_job_soft_limit: int = 40

    @property
    def workspace_arm_id(self) -> str:
        return (f"/subscriptions/{self.subscription_id}/resourceGroups/{self.resource_group}"
                f"/providers/Microsoft.OperationalInsights/workspaces/{self.workspace_name}")

    @property
    def live_ready(self) -> list[str]:
        """Missing settings for live mode (empty list = ready)."""
        need = {"LAKEHUNT_SUBSCRIPTION_ID": self.subscription_id, "LAKEHUNT_RESOURCE_GROUP": self.resource_group,
                "LAKEHUNT_WORKSPACE_NAME": self.workspace_name, "LAKEHUNT_WORKSPACE_ID": self.workspace_id}
        return [k for k, v in need.items() if not v]


settings = Settings()
