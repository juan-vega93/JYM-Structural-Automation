"""Plastic flexural yielding only; no code applicability or stability checks."""

from typing import Literal

from jym_structural.core import CapacityValue, MaterialProperties, PropertySource, SectionProperties

from ._validation import require_mpa_mm, validate_positive_factor


def _moment_unit(stress: str, length: str) -> str:
    # MPa = N/mm^2, and the supplied plastic modulus is in mm^3.
    require_mpa_mm(stress, length)
    return "N*mm"


def steel_flexural_yield_capacity(
    material: MaterialProperties,
    section: SectionProperties,
    *,
    component: Literal["m2", "m3"],
    section_axis: Literal["x", "y"],
    factor: float,
    member_id: str | None = None,
    source: PropertySource | None = None,
) -> CapacityValue:
    """Return factor * Fy * Z in N*mm for exact MPa/mm inputs.

    The caller independently specifies the demand component and section axis;
    x selects zx and y selects zy, with no local-axis orientation inference.
    Factor has no code-defined meaning here. This calculation does not determine
    whether using Z is applicable under a design standard. Source is caller supplied.
    """
    if component not in ("m2", "m3"):
        raise ValueError(f"Unsupported flexural component: {component!r}; expected m2 or m3")
    if section_axis not in ("x", "y"):
        raise ValueError(f"Unsupported section axis: {section_axis!r}; expected x or y")
    factor = validate_positive_factor(factor)
    if not isinstance(material, MaterialProperties) or not isinstance(section, SectionProperties):
        raise TypeError("Expected MaterialProperties and SectionProperties")
    # Revalidate existing instances too: model_copy(update=...) can bypass validation.
    material = MaterialProperties.model_validate(material)
    section = SectionProperties.model_validate(section)
    unit = _moment_unit(material.units.stress, section.units.length)
    z = section.zx if section_axis == "x" else section.zy
    return CapacityValue(
        component=component,
        value=factor * material.fy * z,
        unit=unit,
        limit_state="steel_flexural_yielding",
        member_id=member_id,
        section_name=section.name,
        material_name=material.name,
        source=source,
    )
