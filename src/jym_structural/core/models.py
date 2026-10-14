from __future__ import annotations

from pydantic import BaseModel, Field


class ModelInfo(BaseModel):
    software: str
    version: str | None = None
    model_name: str | None = None
    model_path: str | None = None
    units: str | None = None


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
