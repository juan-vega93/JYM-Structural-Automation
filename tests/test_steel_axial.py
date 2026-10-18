import subprocess
import sys

import pytest
from pydantic import ValidationError

from jym_structural.core import (
    CapacityValue,
    DemandCheck,
    ForceExtreme,
    FrameForces,
    MaterialProperties,
    MaterialUnits,
    PropertySource,
    ResultUnits,
    SectionProperties,
    SectionUnits,
    demand_ratio,
)
from jym_structural.design.steel import steel_axial_yield_capacity


@pytest.fixture
def material():
    return MaterialProperties(
        name=" synthetic steel ",
        fy=250,
        fu=400,
        elastic_modulus=200000,
        shear_modulus=77000,
        units=MaterialUnits(stress="MPa"),
        source=PropertySource(kind="manual", name="material data"),
    )


@pytest.fixture
def section():
    # Synthetic supplied properties, not a real profile or verified catalog entry.
    return SectionProperties(
        name=" synthetic section ",
        area=10_000,
        ix=900,
        iy=400,
        sx=7,
        sy=11,
        zx=1_000_000,
        zy=250_000,
        rx=3,
        ry=2,
        j=10,
        cw=0,
        units=SectionUnits(length="mm"),
        source=PropertySource(kind="catalog", name="section data"),
    )


@pytest.mark.parametrize("factor,expected", [(0.9, 2_250_000), (1.0, 2_500_000), (1, 2_500_000)])
def test_axial_capacity_exact_magnitude_and_metadata(material, section, factor, expected):
    result = steel_axial_yield_capacity(material, section, factor=factor)
    assert type(result) is CapacityValue
    assert result.value == expected
    assert result.component == "p"
    assert result.unit == "N"
    assert result.limit_state == "steel_axial_yielding"
    assert result.section_name == section.name
    assert result.material_name == material.name
    assert result.member_id is None
    assert result.source is None  # Property origins are not calculation provenance.


@pytest.mark.parametrize("fy,area,expected", [(300, 10_000, 3_000_000), (250, 1_000, 250_000)])
def test_uses_supplied_fy_and_area(material, section, fy, area, expected):
    material = MaterialProperties.model_validate({**material.model_dump(), "fy": fy})
    section = SectionProperties.model_validate({**section.model_dump(), "area": area})
    assert steel_axial_yield_capacity(material, section, factor=1).value == expected


def test_other_properties_do_not_determine_capacity(material, section):
    other_material = MaterialProperties.model_validate(
        {
            **material.model_dump(),
            "fu": 500,
            "elastic_modulus": 210000,
            "shear_modulus": 80000,
        }
    )
    other_section = SectionProperties.model_validate(
        {
            **section.model_dump(),
            "ix": 100,
            "iy": 200,
            "rx": 10,
            "ry": 20,
            "zx": 1,
            "zy": 2,
            "sx": 3,
            "sy": 4,
        }
    )
    assert steel_axial_yield_capacity(material, section, factor=1) == steel_axial_yield_capacity(
        other_material,
        other_section,
        factor=1,
    )


@pytest.mark.parametrize(
    "factor", [0, -1, float("nan"), float("inf"), -float("inf"), True, False, "0.9", None]
)
def test_invalid_factor(material, section, factor):
    with pytest.raises(ValidationError):
        steel_axial_yield_capacity(material, section, factor=factor)


def test_factor_required(material, section):
    with pytest.raises(TypeError):
        steel_axial_yield_capacity(material, section)


@pytest.mark.parametrize(
    "stress,length",
    [
        ("MPa", "m"),
        ("ksi", "in"),
        ("kgf/cm²", "cm"),
        ("kgf/cm^2", "cm"),
        ("mpa", "mm"),
        ("MPa", "MM"),
        ("MPa ", "mm"),
        ("MPa", " mm"),
    ],
)
def test_unsupported_units(material, section, stress, length):
    material = MaterialProperties.model_validate(
        {**material.model_dump(), "units": {"stress": stress}}
    )
    section = SectionProperties.model_validate(
        {**section.model_dump(), "units": {"length": length}}
    )
    with pytest.raises(ValueError, match="Unsupported unit combination"):
        steel_axial_yield_capacity(material, section, factor=1)


@pytest.mark.parametrize("target", ["material", "section"])
@pytest.mark.parametrize("bad", [None, {}, "properties"])
def test_wrong_input_type(material, section, target, bad):
    with pytest.raises(TypeError, match="Expected MaterialProperties and SectionProperties"):
        steel_axial_yield_capacity(
            bad if target == "material" else material,
            bad if target == "section" else section,
            factor=1,
        )


@pytest.mark.parametrize(
    "target,field,value",
    [
        ("material", "fy", -1),
        ("material", "fy", float("nan")),
        ("section", "area", 0),
        ("section", "area", -1),
        ("material", "units", MaterialUnits(stress="MPa").model_copy(update={"stress": ""})),
        ("section", "units", SectionUnits(length="mm").model_copy(update={"length": ""})),
    ],
)
def test_revalidates_unchecked_copies(material, section, target, field, value):
    if target == "material":
        material = material.model_copy(update={field: value})
    else:
        section = section.model_copy(update={field: value})
    with pytest.raises(ValidationError):
        steel_axial_yield_capacity(material, section, factor=1)


@pytest.mark.parametrize("factor", [1e308, 5e-324])
def test_invalid_product_rejected(material, section, factor):
    if factor < 1:
        material = MaterialProperties.model_validate({**material.model_dump(), "fy": 1e-300})
        section = SectionProperties.model_validate({**section.model_dump(), "area": 1e-300})
    with pytest.raises(ValidationError):
        steel_axial_yield_capacity(material, section, factor=factor)


def test_provenance_purity_repeatability_frozen_and_json(material, section):
    source = PropertySource(kind="manual", name="caller calculation", version="A0.7")
    before = [value.model_dump_json() for value in (material, section, source)]
    result = steel_axial_yield_capacity(
        material, section, factor=0.9, member_id=" 012 ", source=source
    )
    assert result.member_id == " 012 "
    assert result.source == source
    assert result == steel_axial_yield_capacity(
        material,
        section,
        factor=0.9,
        member_id=" 012 ",
        source=source,
    )
    assert before == [value.model_dump_json() for value in (material, section, source)]
    assert CapacityValue.model_validate_json(result.model_dump_json()) == result
    with pytest.raises(ValidationError, match="frozen"):
        result.value = 1


def extreme(value=125_000, component="p", member_id="12", force="N"):
    return ForceExtreme(
        member_id=member_id,
        component=component,
        kind="absolute",
        source=FrameForces(
            object_id=member_id,
            station=0,
            element_id="e1",
            element_station=0,
            load_case="synthetic",
            step_num=0,
            **{component: value},
        ),
        units=ResultUnits(force=force, length="mm"),
    )


@pytest.mark.parametrize(
    "value,ratio,passes",
    [
        (125_000, 0.5, True),
        (-125_000, 0.5, True),
        (250_000, 1, True),
        (-250_000, 1, True),
        (375_000, 1.5, False),
        (-375_000, 1.5, False),
    ],
)
def test_neutral_end_to_end_signed_demands(material, section, value, ratio, passes):
    section = SectionProperties.model_validate({**section.model_dump(), "area": 1_000})
    capacity = steel_axial_yield_capacity(material, section, factor=1, member_id="12")
    assert capacity.value == 250_000
    check = demand_ratio(extreme(value), capacity)
    assert check.ratio == ratio
    assert check.passes is passes
    assert check.demand.value == value
    assert DemandCheck.model_validate_json(check.model_dump_json()) == check


@pytest.mark.parametrize(
    "changes,error",
    [
        ({"member_id": "15"}, "member_id must match"),
        ({"component": "m3"}, "components must match"),
        ({"force": "kN"}, "unit labels must match"),
    ],
)
def test_check_mismatches(material, section, changes, error):
    capacity = steel_axial_yield_capacity(material, section, factor=1, member_id="12")
    with pytest.raises(ValidationError, match=error):
        demand_ratio(extreme(**changes), capacity)


def test_import_steel_without_adapters_or_comtypes():
    script = """
import sys
from jym_structural.design.steel import steel_axial_yield_capacity, steel_flexural_yield_capacity
assert not any(n.startswith('jym_structural.adapters') for n in sys.modules)
assert not any(n == 'comtypes' or n.startswith('comtypes.') for n in sys.modules)
"""
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)
