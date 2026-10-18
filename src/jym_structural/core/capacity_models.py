"""Supplied structural capacity results, not resistance calculations."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat

from .models import ForceComponent
from .property_models import PropertySource

_NonBlank = Annotated[str, Field(min_length=1, pattern=r"\S")]


class CapacityValue(BaseModel):
    """Positive available magnitude with exact unit label and uninterpreted metadata.

    Optional member, section and material references do not resolve themselves.
    source is absent when unknown; never infer a provider or a design method.
    """

    model_config = ConfigDict(
        frozen=True,
        strict=True,
        extra="forbid",
        revalidate_instances="always",
    )

    component: ForceComponent
    value: FiniteFloat = Field(gt=0)
    unit: _NonBlank
    limit_state: _NonBlank
    member_id: _NonBlank | None = None
    section_name: _NonBlank | None = None
    material_name: _NonBlank | None = None
    source: PropertySource | None = None
