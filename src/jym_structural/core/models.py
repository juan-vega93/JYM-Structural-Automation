from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, computed_field, model_validator


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
    """One local-axis force row; station is measured from the object's I-end.

    element_station is measured from the analysis element's I-end. Keep both:
    an object may span multiple analysis elements. load_case identifies the
    source case OR combination; no envelope is computed by this model.
    """

    model_config = ConfigDict(strict=True)

    object_id: str | None = None
    station: FiniteFloat | None = None
    element_id: str | None = None
    element_station: FiniteFloat | None = None
    load_case: str | None = None
    step_type: str | None = None
    step_num: FiniteFloat | None = None
    p: FiniteFloat | None = None
    v2: FiniteFloat | None = None
    v3: FiniteFloat | None = None
    t: FiniteFloat | None = None
    m2: FiniteFloat | None = None
    m3: FiniteFloat | None = None


class ResultUnits(BaseModel):
    """Source units: forces use force, stations use length, moments use force*length."""

    force: str = Field(min_length=1)
    length: str = Field(min_length=1)

    @computed_field
    @property
    def moment(self) -> str:
        return f"{self.force}*{self.length}"


class AnalysisResult(BaseModel):
    member_id: str
    forces: list[FrameForces] = Field(default_factory=list)
    units: ResultUnits | None = None
    u1: float | None = None
    u2: float | None = None
    u3: float | None = None
