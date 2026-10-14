from __future__ import annotations

from typing import Protocol

from jym_structural.core.models import AnalysisResult, Member, ModelInfo, Section


class Sap2000Gateway(Protocol):
    """Boundary for SAP2000 integration.

    Concrete COM/OAPI implementation comes later. Keeping the boundary here lets
    tests, MCP tools and workflows depend on a stable contract instead of CSI COM.
    """

    def connect_to_running_instance(self) -> ModelInfo: ...

    def health_check(self) -> bool: ...

    def list_sections(self) -> list[Section]: ...

    def list_members(self) -> list[Member]: ...

    def run_analysis(self) -> None: ...

    def get_member_results(self, member_id: str) -> AnalysisResult: ...
