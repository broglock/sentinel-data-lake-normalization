"""Provider interface: everything the app needs from a workspace and its lake."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Provider(ABC):
    mode = "base"

    # ---- workspace inventory
    @abstractmethod
    def tables(self) -> list[dict]: ...
    @abstractmethod
    def sample(self, table: str, n: int = 500) -> list[dict]: ...

    # ---- index
    @abstractmethod
    def reindex(self, groups: list[dict], vocab: dict) -> dict: ...
    @abstractmethod
    def coverage(self, groups: list[dict]) -> list[dict]: ...
    @abstractmethod
    def history(self, group: dict) -> list[dict]: ...

    # ---- hunting
    @abstractmethod
    def hunt(self, tool: str, **params: Any) -> list[dict]: ...
    @abstractmethod
    def index_rows_for_group(self, group_id: str, limit: int = 20) -> list[dict]: ...
    @abstractmethod
    def pivot(self, table: str, event_time: str, value: str, record_key: str = "", group: dict | None = None) -> list[dict]: ...

    # ---- tenant changes (only ever called after an approval)
    @abstractmethod
    def installed_solutions(self) -> list[dict]: ...
    @abstractmethod
    def install_solution(self, solution: dict) -> dict: ...
    @abstractmethod
    def create_table(self, name: str, columns: list[dict], plan: str, retention_days: int) -> dict: ...

    # ---- validation helpers
    @abstractmethod
    def canary(self, group: dict, vocab: dict, value: str | None = None) -> dict: ...
