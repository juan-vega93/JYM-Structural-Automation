"""Neutral physical properties: explicit units and provenance, no design capacities."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator

_NonBlank = Annotated[str, Field(min_length=1, pattern=r"\S")]
_Positive = Annotated[FiniteFloat, Field(gt=0)]


class _PropertyValue(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        strict=True,
        extra="forbid",
        revalidate_instances="always",
    )


class PropertySource(_PropertyValue):
    kind: Literal["manual", "catalog", "solver", "bim", "imported"]
    name: _NonBlank | None = None
    version: _NonBlank | None = None


class MaterialUnits(_PropertyValue):
    stress: _NonBlank


class MaterialProperties(_PropertyValue):
    """Supplied material data, all stresses/moduli in units.stress."""

    name: _NonBlank
    fy: _Positive
    fu: _Positive
    elastic_modulus: _Positive
    shear_modulus: _Positive
    poisson_ratio: Annotated[FiniteFloat, Field(ge=0, lt=0.5)] | None = None
    units: MaterialUnits
    source: PropertySource | None = None

    @model_validator(mode="after")
    def validate_strength_order(self) -> Self:
        if self.fu < self.fy:
            raise ValueError("fu must be greater than or equal to fy")
        return self


class SectionUnits(_PropertyValue):
    """Only length is stored/serialized; dimensional powers cannot be supplied."""

    length: _NonBlank

    @property
    def area(self) -> str:
        return f"{self.length}^2"

    @property
    def inertia(self) -> str:
        return f"{self.length}^4"

    @property
    def section_modulus(self) -> str:
        return f"{self.length}^3"

    @property
    def warping(self) -> str:
        return f"{self.length}^6"


class SectionProperties(_PropertyValue):
    """Catalog x/y section axes; no association to member local 2/3 axes.

    rx/ry and optional dimensions use length; area uses length^2; ix/iy/j
    use length^4; sx/sy/zx/zy use length^3; cw uses length^6.
    """

    name: _NonBlank
    area: _Positive
    ix: _Positive
    iy: _Positive
    sx: _Positive
    sy: _Positive
    zx: _Positive
    zy: _Positive
    rx: _Positive
    ry: _Positive
    j: _Positive
    cw: Annotated[FiniteFloat, Field(ge=0)]
    d: _Positive | None = None
    bf: _Positive | None = None
    tf: _Positive | None = None
    tw: _Positive | None = None
    section_type: _NonBlank | None = None
    material_name: _NonBlank | None = None
    units: SectionUnits
    source: PropertySource | None = None
