from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator


class ModelInfo(BaseModel):
    software: str
    version: str | None = None
    model_name: str | None = None
    model_path: str | None = None
    units: str | None = None


class Point3D(BaseModel):
    """Finite Cartesian coordinates in the containing model's length unit."""

    model_config = ConfigDict(strict=True)

    x: FiniteFloat
    y: FiniteFloat
    z: FiniteFloat


class Node(BaseModel):
    id: str = Field(min_length=1)
    position: Point3D


class Section(BaseModel):
    name: str
    material: str | None = None
    family: str | None = None


class Member(BaseModel):
    id: str
    name: str
    section: str | None = None
    start_node: str | None = None
    end_node: str | None = None
    length: float | None = Field(default=None, ge=0)


class StructuralModel(BaseModel):
    """Neutral geometry snapshot; all positions and lengths use length_unit.

    Section.name is the section identifier. Members reference nodes and sections
    by identifier; lists retain duplicates until validation can reject them.
    """

    model_info: ModelInfo
    length_unit: str = Field(min_length=1, pattern=r"\S")
    nodes: list[Node] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)
    members: list[Member] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_topology(self) -> Self:
        for label, identifiers in (
            ("node", [node.id for node in self.nodes]),
            ("member", [member.id for member in self.members]),
            ("section", [section.name for section in self.sections]),
        ):
            seen: set[str] = set()
            for identifier in identifiers:
                if identifier in seen:
                    raise ValueError(f"Duplicate {label} identifier: {identifier!r}")
                seen.add(identifier)
        node_ids = {node.id for node in self.nodes}
        section_names = {section.name for section in self.sections}
        for member in self.members:
            for endpoint in ("start_node", "end_node"):
                identifier = getattr(member, endpoint)
                if identifier not in node_ids:
                    raise ValueError(
                        f"Member {member.id!r} {endpoint} references missing node {identifier!r}"
                    )
            if member.section is not None and member.section not in section_names:
                raise ValueError(
                    f"Member {member.id!r} references missing section {member.section!r}"
                )
        return self


class FrameForces(BaseModel):
    station: float | None = None
    load_case: str | None = None
    p: float | None = None
    v2: float | None = None
    v3: float | None = None
    t: float | None = None
    m2: float | None = None
    m3: float | None = None


class AnalysisResult(BaseModel):
    member_id: str
    forces: list[FrameForces] = Field(default_factory=list)
    u1: float | None = None
    u2: float | None = None
    u3: float | None = None
