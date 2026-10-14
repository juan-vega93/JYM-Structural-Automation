from __future__ import annotations

from typing import Protocol

from jym_structural.core.models import AnalysisResult, Member, ModelInfo, Section, StructuralModel


class Sap2000ConnectionGateway(Protocol):
    """Read-only connection and health capability for B1.1."""

    def connect_to_running_instance(self) -> ModelInfo: ...

    def health_check(self) -> bool: ...


class Sap2000ModelReader(Protocol):
    """Read-only model capability, separate from connection."""

    def list_sections(self) -> list[Section]: ...

    def list_members(self) -> list[Member]: ...

    def read_structural_model(self) -> StructuralModel: ...


class Sap2000AnalysisRunner(Protocol):
    """Explicit analysis command capability."""

    def run_analysis(self) -> None: ...


class Sap2000ResultsReader(Protocol):
    """Read-only member results capability."""

    def get_member_results(self, member_id: str) -> AnalysisResult: ...
