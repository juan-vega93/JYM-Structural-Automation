import math
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
from jym_structural.design.steel import steel_euler_buckling_capacity


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
    # Synthetic supplied data; no catalog or geometric consistency assertion.
    return SectionProperties(
        name=" synthetic section ",
        area=10000,
        ix=900,
        iy=400,
        sx=7,
        sy=11,
        zx=1000,
        zy=250,
        rx=100,
        ry=50,
        j=10,
        cw=0,
        units=SectionUnits(length="mm"),
        source=PropertySource(kind="catalog", name="section data"),
    )


def calculate(material, section, **changes):
    options = {"axis": "x", "length": 3000, "k_factor": 1, "factor": 1}
    options.update(changes)
    return steel_euler_buckling_capacity(material, section, **options)


@pytest.mark.parametrize("axis,radius", [("x", 100), ("y", 50)])
@pytest.mark.parametrize("factor", [1, 1.0, 0.9])
def test_euler_formula_and_metadata(material, section, axis, radius, factor):
    result = calculate(material, section, axis=axis, factor=factor)
    expected = factor * math.pi**2 * 200000 * 10000 / (1 * 3000 / radius) ** 2
    assert type(result) is CapacityValue
    assert result.value == pytest.approx(expected)
    assert result.component == "p"
    assert result.unit == "N"
    assert result.limit_state == "steel_euler_buckling"
    assert result.section_name == section.name
    assert result.material_name == material.name
    assert result.member_id is result.source is None


@pytest.mark.parametrize("axis", ["X", "z", "", None])
def test_invalid_axis(material, section, axis):
    with pytest.raises(ValueError, match="Unsupported buckling axis"):
        calculate(material, section, axis=axis)


@pytest.mark.parametrize("field", ["length", "k_factor", "factor"])
@pytest.mark.parametrize(
    "value", [0, -1, float("nan"), float("inf"), -float("inf"), True, False, "1", None]
)
def test_invalid_strict_scalars(material, section, field, value):
    with pytest.raises(ValidationError):
        calculate(material, section, **{field: value})


@pytest.mark.parametrize("field", ["axis", "length", "k_factor", "factor"])
def test_required_explicit_parameters(material, section, field):
    options = {"axis": "x", "length": 3000, "k_factor": 1, "factor": 1}
    options.pop(field)
    with pytest.raises(TypeError):
        steel_euler_buckling_capacity(material, section, **options)


@pytest.mark.parametrize(
    "stress,length",
    [("MPa", "m"), ("ksi", "in"), ("kgf/cm²", "cm"), ("MPa ", "mm"), ("mpa", "mm"), ("MPa", "MM")],
)
def test_unsupported_units(material, section, stress, length):
    material = MaterialProperties.model_validate(
        {**material.model_dump(), "units": {"stress": stress}}
    )
    section = SectionProperties.model_validate(
        {**section.model_dump(), "units": {"length": length}}
    )
    with pytest.raises(ValueError, match="Unsupported unit combination"):
        calculate(material, section)


@pytest.mark.parametrize("target", ["material", "section"])
def test_wrong_input_types(material, section, target):
    with pytest.raises(TypeError, match="Expected MaterialProperties and SectionProperties"):
        calculate(
            {} if target == "material" else material, None if target == "section" else section
        )


@pytest.mark.parametrize(
    "target,field,value",
    [
        ("material", "elastic_modulus", 0),
        ("material", "elastic_modulus", -1),
        ("section", "area", 0),
        ("section", "rx", 0),
        ("section", "ry", -1),
        ("material", "units", MaterialUnits(stress="MPa").model_copy(update={"stress": ""})),
        ("section", "units", SectionUnits(length="mm").model_copy(update={"length": ""})),
    ],
)
def test_revalidates_unchecked_properties(material, section, target, field, value):
    if target == "material":
        material = material.model_copy(update={field: value})
    else:
        section = section.model_copy(update={field: value})
    with pytest.raises(ValidationError):
        calculate(material, section)


@pytest.mark.parametrize(
    "field,value", [("fy", 300), ("fu", 500), ("shear_modulus", 90000), ("poisson_ratio", 0.3)]
)
def test_unrelated_material_properties_do_not_change_euler(material, section, field, value):
    changed = MaterialProperties.model_validate({**material.model_dump(), field: value})
    assert calculate(changed, section) == calculate(material, section)


@pytest.mark.parametrize("field", ["ix", "iy", "zx", "zy", "sx", "sy", "j", "cw"])
def test_unrelated_section_properties_do_not_change_euler(material, section, field):
    changed = SectionProperties.model_validate({**section.model_dump(), field: 123})
    assert calculate(material, changed) == calculate(material, section)


@pytest.mark.parametrize("axis,field", [("x", "ry"), ("y", "rx")])
def test_other_radius_never_selects_critical_axis(material, section, axis, field):
    changed = SectionProperties.model_validate({**section.model_dump(), field: 0.01})
    assert calculate(material, changed, axis=axis) == calculate(material, section, axis=axis)


@pytest.mark.parametrize("axis", ["x", "y"])
@pytest.mark.parametrize(
    "quantity,multiplier",
    [("length", 0.25), ("k_factor", 0.25), ("radius", 4), ("area", 2), ("E", 2)],
)
def test_physical_scaling_relations(material, section, axis, quantity, multiplier):
    baseline = calculate(material, section, axis=axis).value
    changes = {"axis": axis}
    if quantity == "length":
        changes["length"] = 6000
    elif quantity == "k_factor":
        changes["k_factor"] = 2
    elif quantity == "E":
        material = MaterialProperties.model_validate(
            {**material.model_dump(), "elastic_modulus": 400000}
        )
    else:
        field = "area" if quantity == "area" else ("rx" if axis == "x" else "ry")
        section = SectionProperties.model_validate(
            {**section.model_dump(), field: 2 * getattr(section, field)}
        )
    assert calculate(material, section, **changes).value == pytest.approx(baseline * multiplier)


def test_euler_is_not_capped_by_yield(material, section):
    result = calculate(material, section)
    assert result.value / section.area > material.fy
    assert result.value > material.fy * section.area


@pytest.mark.parametrize(
    "changes",
    [
        {"length": 1e308, "k_factor": 1e308},  # Slenderness overflow.
        {"length": 5e-324, "k_factor": 5e-324},  # Slenderness zero.
        {"length": 1e200},  # Squared slenderness overflow.
        {"length": 1e-200},  # Squared slenderness zero.
        {"factor": 1e308},  # Final capacity overflow.
    ],
)
def test_invalid_arithmetic_rejected(material, section, changes):
    with pytest.raises(ValidationError):
        calculate(material, section, **changes)


def test_final_capacity_underflow_rejected(material, section):
    material = MaterialProperties.model_validate(
        {**material.model_dump(), "elastic_modulus": 1e-300}
    )
    with pytest.raises(ValidationError):
        calculate(material, section, factor=5e-324)


def test_provenance_purity_repeatability_frozen_and_roundtrip(material, section):
    source = PropertySource(kind="manual", name="caller calculation", version="A0.8")
    before = [v.model_dump_json() for v in (material, section, source)]
    result = calculate(material, section, source=source, member_id=" 012 ")
    assert result.source == source
    assert result.member_id == " 012 "
    assert result == calculate(material, section, source=source, member_id=" 012 ")
    assert before == [v.model_dump_json() for v in (material, section, source)]
    assert CapacityValue.model_validate_json(result.model_dump_json()) == result
    with pytest.raises(ValidationError, match="frozen"):
        result.value = 1


def extreme(value, component="p", member_id="12", force="N"):
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


@pytest.mark.parametrize("sign", [1, -1])
def test_neutral_end_to_end_signed_demand(material, section, sign):
    capacity = calculate(material, section, member_id="12")
    demand = extreme(sign * capacity.value / 2)
    check = demand_ratio(demand, capacity)
    assert check.ratio == pytest.approx(0.5)
    assert check.passes
    assert check.demand.value == demand.value
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
    capacity = calculate(material, section, member_id="12")
    with pytest.raises(ValidationError, match=error):
        demand_ratio(extreme(100, **changes), capacity)


def test_import_without_adapters_or_comtypes():
    script = """
import sys
from jym_structural.design.steel import (
    steel_euler_buckling_capacity, steel_axial_yield_capacity, steel_flexural_yield_capacity,
)
assert not any(n.startswith('jym_structural.adapters') for n in sys.modules)
assert not any(n == 'comtypes' or n.startswith('comtypes.') for n in sys.modules)
"""
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)
