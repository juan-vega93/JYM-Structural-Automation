"""Axial yield magnitude only; no fracture, stability or code applicability checks."""

from jym_structural.core import CapacityValue, MaterialProperties, PropertySource, SectionProperties

from ._validation import require_mpa_mm, validate_positive_factor


def steel_axial_yield_capacity(
    material: MaterialProperties,
    section: SectionProperties,
    *,
    factor: float,
    member_id: str | None = None,
    source: PropertySource | None = None,
) -> CapacityValue:
    """Return factor * Fy * supplied area in N for exact MPa/mm inputs.

    Factor has no implied normative meaning. The positive magnitude can be
    compared with either demand sign, without constituting a compression
    buckling or tension fracture check. Calculation provenance is caller supplied.
    """
    factor = validate_positive_factor(factor)
    if not isinstance(material, MaterialProperties) or not isinstance(section, SectionProperties):
        raise TypeError("Expected MaterialProperties and SectionProperties")
    # Revalidate even frozen instances: unchecked model copies can contain invalid data.
    material = MaterialProperties.model_validate(material)
    section = SectionProperties.model_validate(section)
    require_mpa_mm(material.units.stress, section.units.length)
    # MPa = N/mm^2 and the supplied area is in mm^2: no numeric scale change.
    return CapacityValue(
        component="p",
        value=factor * material.fy * section.area,
        unit="N",
        limit_state="steel_axial_yielding",
        member_id=member_id,
        section_name=section.name,
        material_name=material.name,
        source=source,
    )
