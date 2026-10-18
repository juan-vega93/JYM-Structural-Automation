"""Ideal elastic Euler buckling only, without yield caps or inelastic curves."""

import math
from typing import Literal

from jym_structural.core import CapacityValue, MaterialProperties, PropertySource, SectionProperties

from ._validation import require_mpa_mm, validate_positive_factor, validate_positive_scalar


def steel_euler_buckling_capacity(
    material: MaterialProperties,
    section: SectionProperties,
    *,
    axis: Literal["x", "y"],
    length: float,
    k_factor: float,
    factor: float,
    member_id: str | None = None,
    source: PropertySource | None = None,
) -> CapacityValue:
    """Return factor * (pi^2 * E / (K*L/r)^2) * A in N.

    Length uses section.units.length (only mm is supported with MPa).
    Axis x selects rx, y selects ry; no critical axis or support is inferred.
    Euler is returned even when Fe exceeds Fy; this is not code compression design.
    """
    if axis not in ("x", "y"):
        raise ValueError(f"Unsupported buckling axis: {axis!r}; expected x or y")
    length = validate_positive_scalar(length)
    k_factor = validate_positive_scalar(k_factor)
    factor = validate_positive_factor(factor)
    if not isinstance(material, MaterialProperties) or not isinstance(section, SectionProperties):
        raise TypeError("Expected MaterialProperties and SectionProperties")
    material = MaterialProperties.model_validate(material)
    section = SectionProperties.model_validate(section)
    require_mpa_mm(material.units.stress, section.units.length)
    radius = section.rx if axis == "x" else section.ry
    slenderness = validate_positive_scalar(k_factor * length / radius)
    # Multiplication yields Inf on overflow, allowing explicit finite validation;
    # validating the denominator also rejects zero before any division occurs.
    slenderness_squared = validate_positive_scalar(slenderness * slenderness)
    fe = validate_positive_scalar(math.pi**2 * material.elastic_modulus / slenderness_squared)
    pcr = validate_positive_scalar(fe * section.area)
    return CapacityValue(
        component="p",
        value=factor * pcr,
        unit="N",
        limit_state="steel_euler_buckling",
        member_id=member_id,
        section_name=section.name,
        material_name=material.name,
        source=source,
    )
