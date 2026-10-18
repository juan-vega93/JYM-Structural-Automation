"""Traceable, solver-neutral force processing outputs."""

from __future__ import annotations

import math
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    computed_field,
    field_validator,
    model_validator,
)

from .capacity_models import CapacityValue
from .models import ForceComponent, FrameForces, ResultUnits

ExtremeKind = Literal["min", "max", "absolute"]


class ForceExtreme(BaseModel):
    """Detached source snapshot; value and unit derive from its component.

    The wrapper is frozen. Nested source/units remain serializable Core models;
    callers must treat the snapshot as a value, not edit its nested objects.
    """

    model_config = ConfigDict(frozen=True)

    member_id: str = Field(min_length=1)
    component: ForceComponent
    kind: ExtremeKind
    source: FrameForces
    units: ResultUnits

    @field_validator("source", "units", mode="before")
    @classmethod
    def detach_snapshot(cls, value: object) -> object:
        # Revalidate even existing instances, which may have been edited since
        # construction. A fresh dictionary also prevents aliasing the input.
        if isinstance(value, (FrameForces, ResultUnits)):
            return value.model_dump(round_trip=True)
        return value

    @model_validator(mode="after")
    def validate_source(self) -> Self:
        if not self.member_id.strip():
            raise ValueError("member_id must be nonblank")
        for field in ("object_id", "element_id", "load_case"):
            value = getattr(self.source, field)
            if value is None or not value.strip():
                raise ValueError(f"Source {field} is required and must be nonblank")
        if self.source.object_id != self.member_id:
            raise ValueError("Source object_id must match member_id")
        for field in ("station", "element_station", "step_num", self.component):
            if getattr(self.source, field) is None:
                raise ValueError(f"Source {field} is required")
        if not self.units.force.strip() or not self.units.length.strip():
            raise ValueError("Force and length units must be nonblank")
        return self

    @computed_field
    @property
    def value(self) -> FiniteFloat:
        # The selected component is non-null after validation; do not duplicate
        # its value in another writable field.
        return getattr(self.source, self.component)

    @computed_field
    @property
    def unit(self) -> str:
        return self.units.force if self.component in ("p", "v2", "v3") else self.units.moment


class ForceEnvelope(BaseModel):
    """Two independent source rows for one component of one member."""

    model_config = ConfigDict(frozen=True)

    component: ForceComponent
    minimum: ForceExtreme
    maximum: ForceExtreme

    @field_validator("minimum", "maximum", mode="before")
    @classmethod
    def detach_extreme(cls, value: object) -> object:
        if isinstance(value, ForceExtreme):
            return value.model_dump(round_trip=True)
        return value

    @model_validator(mode="after")
    def validate_extremes(self) -> Self:
        if self.minimum.component != self.component or self.maximum.component != self.component:
            raise ValueError("Envelope components must agree")
        if self.minimum.kind != "min" or self.maximum.kind != "max":
            raise ValueError("Envelope requires min and max extremes")
        if self.minimum.member_id != self.maximum.member_id:
            raise ValueError("Envelope member IDs must agree")
        if self.minimum.units != self.maximum.units:
            raise ValueError("Envelope units must agree")
        if self.minimum.value > self.maximum.value:
            raise ValueError("Envelope minimum exceeds maximum")
        return self


class DemandCheck(BaseModel):
    """Traceable comparison with exact component, unit and optional member agreement."""

    model_config = ConfigDict(frozen=True)

    demand: ForceExtreme
    capacity: CapacityValue

    @field_validator("demand", "capacity", mode="before")
    @classmethod
    def detach_inputs(cls, value: object) -> object:
        if isinstance(value, (ForceExtreme, CapacityValue)):
            return value.model_dump(round_trip=True)
        return value

    @model_validator(mode="after")
    def validate_ratio(self) -> Self:
        if self.demand.component != self.capacity.component:
            raise ValueError("Demand and capacity components must match")
        if self.demand.unit != self.capacity.unit:
            raise ValueError("Demand and capacity unit labels must match exactly")
        if self.capacity.member_id is not None and self.capacity.member_id != self.demand.member_id:
            raise ValueError("Capacity member_id must match demand member_id when supplied")
        if not math.isfinite(self.ratio):
            raise ValueError("Demand ratio must be finite")
        return self

    @computed_field
    @property
    def ratio(self) -> float:
        return abs(self.demand.value) / self.capacity.value

    @computed_field
    @property
    def passes(self) -> bool:
        return self.ratio <= 1.0
