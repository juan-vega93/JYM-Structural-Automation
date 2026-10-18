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
from jym_structural.design.steel import steel_flexural_yield_capacity


@pytest.fixture
def material():
    return MaterialProperties(
        name="synthetic steel",
        fy=250,
        fu=400,
        elastic_modulus=200000,
        shear_modulus=77000,
        units=MaterialUnits(stress="MPa"),
        source=PropertySource(kind="manual", name="property source"),
    )


@pytest.fixture
def section():
    # Explicit synthetic values, not a real profile or validated catalog dataset.
    return SectionProperties(
        name="synthetic section",
        area=100,
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
    )


def calculate(material, section, **changes):
    options = {"component": "m3", "section_axis": "x", "factor": 0.9}
    options.update(changes)
    return steel_flexural_yield_capacity(material, section, **options)


@pytest.mark.parametrize("component", ["m2", "m3"])
@pytest.mark.parametrize(
    "axis,factor,expected", [("x", 0.9, 225_000_000), ("x", 1, 250_000_000), ("y", 1.0, 62_500_000)]
)
def test_explicit_axis_selects_plastic_modulus(
    material, section, component, axis, factor, expected
):
    result = calculate(material, section, component=component, section_axis=axis, factor=factor)
    assert type(result) is CapacityValue
    assert result.value == expected
    assert result.unit == "N*mm"
    assert result.component == component
    assert result.limit_state == "steel_flexural_yielding"
    assert result.section_name == section.name
    assert result.material_name == material.name
    assert result.member_id is result.source is None


def test_provenance_purity_repeatability_and_frozen_output(material, section):
    source = PropertySource(kind="manual", name="calculation supplied by caller", version="A0.6")
    before = [value.model_dump_json() for value in (material, section, source)]
    result = calculate(material, section, source=source, member_id="12")
    assert result == calculate(material, section, source=source, member_id="12")
    assert result.source == source
    assert result.source != material.source
    assert result.member_id == "12"
    assert before == [value.model_dump_json() for value in (material, section, source)]
    assert CapacityValue.model_validate_json(result.model_dump_json()) == result
    with pytest.raises(ValidationError, match="frozen"):
        result.value = 1


@pytest.mark.parametrize("component", ["p", "v2", "v3", "t", "M3", None])
def test_unsupported_component(material, section, component):
    with pytest.raises(ValueError, match="Unsupported flexural component"):
        calculate(material, section, component=component)


@pytest.mark.parametrize("axis", ["z", "X", "", None])
def test_unsupported_axis(material, section, axis):
    with pytest.raises(ValueError, match="Unsupported section axis"):
        calculate(material, section, section_axis=axis)


@pytest.mark.parametrize(
    "factor", [0, -1, float("nan"), float("inf"), -float("inf"), True, False, "0.9", None]
)
def test_invalid_factor(material, section, factor):
    with pytest.raises(ValidationError):
        calculate(material, section, factor=factor)


@pytest.mark.parametrize(
    "stress,length",
    [
        ("MPa", "m"),
        ("ksi", "in"),
        ("kgf/cm^2", "cm"),
        ("kgf/cm²", "cm"),
        ("MPa ", "mm"),
        ("MPa", "MM"),
    ],
)
def test_unsupported_units_are_not_converted(material, section, stress, length):
    material = MaterialProperties.model_validate(
        {**material.model_dump(), "units": {"stress": stress}}
    )
    section = SectionProperties.model_validate(
        {**section.model_dump(), "units": {"length": length}}
    )
    with pytest.raises(ValueError, match="Unsupported unit combination"):
        calculate(material, section)


@pytest.mark.parametrize("field", ["component", "section_axis", "factor"])
def test_mapping_and_factor_have_no_defaults(material, section, field):
    options = {"component": "m3", "section_axis": "x", "factor": 0.9}
    options.pop(field)
    with pytest.raises(TypeError):
        steel_flexural_yield_capacity(material, section, **options)


@pytest.mark.parametrize("factor", [1e308, 5e-324])
def test_nonfinite_or_zero_product_rejected(material, section, factor):
    # Underflow requires small positive Fy/Z as well as a tiny factor.
    if factor < 1:
        material = MaterialProperties.model_validate({**material.model_dump(), "fy": 1e-300})
        section = SectionProperties.model_validate({**section.model_dump(), "zx": 1e-300})
    with pytest.raises(ValidationError):
        calculate(material, section, factor=factor)


@pytest.mark.parametrize("target,field", [("material", "fy"), ("section", "zx")])
def test_invalid_unvalidated_property_copy_rejected(material, section, target, field):
    if target == "material":
        material = material.model_copy(update={field: -1})
    else:
        section = section.model_copy(update={field: -1})
    with pytest.raises(ValidationError):
        calculate(material, section)


def extreme(component="m3", member_id="12", force="N", length="mm"):
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
            **{component: -168_750_000},
        ),
        units=ResultUnits(force=force, length=length),
    )


def test_neutral_end_to_end_check(material, section):
    capacity = calculate(material, section, member_id="12")
    check = demand_ratio(extreme(), capacity)
    assert check.ratio == 0.75
    assert check.passes
    assert check.demand.value == -168_750_000
    assert check.capacity == capacity
    assert DemandCheck.model_validate_json(check.model_dump_json()) == check


@pytest.mark.parametrize(
    "changes,error",
    [
        ({"member_id": "15"}, "member_id must match"),
        ({"component": "m2"}, "components must match"),
        ({"force": "kN", "length": "m"}, "unit labels must match"),
    ],
)
def test_calculated_capacity_keeps_check_compatibility_rules(material, section, changes, error):
    with pytest.raises(ValidationError, match=error):
        demand_ratio(extreme(**changes), calculate(material, section, member_id="12"))


def test_design_import_does_not_load_adapters():
    script = """
import sys
from jym_structural.design.steel import steel_flexural_yield_capacity
assert not any(n.startswith('jym_structural.adapters') for n in sys.modules)
assert 'comtypes' not in sys.modules
"""
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)
