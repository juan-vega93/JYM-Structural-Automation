import subprocess
import sys

import pytest
from pydantic import ValidationError

from jym_structural.core import (
    CapacityValue,
    DemandCheck,
    ForceExtreme,
    FrameForces,
    PropertySource,
    ResultUnits,
    demand_ratio,
)


def capacity(**changes):
    fields = {"component": "m3", "value": 200, "unit": "kN*m", "limit_state": "manual_capacity"}
    fields.update(changes)
    return CapacityValue(**fields)


def demand(component="m3", value=-150):
    return ForceExtreme(
        member_id="12",
        component=component,
        kind="absolute",
        source=FrameForces(
            object_id="12",
            station=0,
            element_id="e1",
            element_station=0,
            load_case="case",
            step_num=0,
            **{component: value},
        ),
        units=ResultUnits(force="kN", length="m"),
    )


@pytest.mark.parametrize("component", ["p", "v2", "v3", "t", "m2", "m3"])
def test_all_components_with_explicit_unit(component):
    extreme = demand(component)
    supplied = capacity(component=component, unit=extreme.unit)
    check = demand_ratio(extreme, supplied)
    assert check.ratio == 0.75
    assert check.passes
    assert check.demand.value == -150
    assert check.capacity.value == 200


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), -float("inf")])
def test_invalid_capacity_value(value):
    with pytest.raises(ValidationError):
        capacity(value=value)


@pytest.mark.parametrize(
    "field", ["unit", "limit_state", "member_id", "section_name", "material_name"]
)
@pytest.mark.parametrize("text", ["", " \t\n"])
def test_blank_labels_and_references(field, text):
    with pytest.raises(ValidationError):
        capacity(**{field: text})


@pytest.mark.parametrize("kind", ["manual", "catalog", "solver", "imported"])
def test_provenance_references_roundtrip_and_deep_copy(kind):
    supplied = capacity(
        source=PropertySource(kind=kind, name="engineering review", version="1"),
        member_id="12",
        section_name="unresolved section",
        material_name="unresolved material",
    )
    assert CapacityValue.model_validate_json(supplied.model_dump_json()) == supplied
    copied = supplied.model_copy(deep=True)
    assert copied == supplied
    assert copied is not supplied
    assert copied.source is not supplied.source
    assert demand_ratio(demand(), supplied).capacity == supplied


def test_optional_metadata_absent_and_arbitrary_limit_state_preserved():
    supplied = capacity(limit_state=" supplied state ")
    assert supplied.limit_state == " supplied state "
    assert supplied.source is None
    assert supplied.member_id is None
    assert supplied.section_name is None
    assert supplied.material_name is None


def test_capacity_and_source_frozen():
    supplied = capacity(source=PropertySource(kind="manual"))
    with pytest.raises(ValidationError, match="frozen"):
        supplied.value = 300
    with pytest.raises(ValidationError, match="frozen"):
        supplied.source.kind = "solver"


def test_component_mismatch():
    with pytest.raises(ValidationError, match="components must match"):
        demand_ratio(demand(), capacity(component="v2"))


@pytest.mark.parametrize("unit", ["kgf*m", "N*m", "kN*mm", "kN·m", " kN*m", "kN*m ", "kN"])
def test_unit_labels_require_exact_equality(unit):
    supplied = capacity(unit=unit)
    assert supplied.unit == unit
    with pytest.raises(ValidationError, match="unit labels must match exactly"):
        demand_ratio(demand(), supplied)


@pytest.mark.parametrize("member_id", [None, "12"])
def test_optional_member_compatible(member_id):
    assert demand_ratio(demand(), capacity(member_id=member_id)).passes


@pytest.mark.parametrize("member_id", ["15", "012", "12 "])
def test_member_requires_exact_equality(member_id):
    with pytest.raises(ValidationError, match="member_id must match"):
        demand_ratio(demand(), capacity(member_id=member_id))


@pytest.mark.parametrize(
    "value,ratio,passes", [(0, 0, True), (-150, 0.75, True), (-200, 1, True), (-250, 1.25, False)]
)
def test_ratio_boundaries_and_signed_demand(value, ratio, passes):
    check = demand_ratio(demand(value=value), capacity())
    assert check.ratio == ratio
    assert check.passes is passes
    assert check.demand.value == value
    assert check.capacity.value > 0
    with pytest.raises(ValidationError, match="frozen"):
        check.ratio = 99


def test_detached_snapshots_no_mutation_and_check_json_roundtrip():
    extreme = demand()
    supplied = capacity(source=PropertySource(kind="manual", name="review"))
    before = (extreme.model_dump(round_trip=True), supplied.model_dump(round_trip=True))
    check = demand_ratio(extreme, supplied)
    assert before == (extreme.model_dump(round_trip=True), supplied.model_dump(round_trip=True))
    assert check.demand is not extreme
    assert check.demand.source is not extreme.source
    assert check.demand.units is not extreme.units
    assert check.capacity is not supplied
    assert check.capacity.source is not supplied.source
    assert DemandCheck.model_validate_json(check.model_dump_json()) == check
    extreme.source.m3 = 12
    extreme.units.force = "kgf"
    assert check.demand.value == -150
    assert check.demand.unit == "kN*m"
    assert check.ratio == 0.75


@pytest.mark.parametrize("value", [0, float("inf")])
def test_check_revalidates_unvalidated_capacity_copy(value):
    supplied = capacity().model_copy(update={"value": value})
    with pytest.raises(ValidationError):
        demand_ratio(demand(), supplied)


def test_ratio_overflow_rejected():
    with pytest.raises(ValidationError, match="ratio must be finite"):
        demand_ratio(demand(value=1e308), capacity(value=1e-308))


def test_core_capacity_cold_import_does_not_load_adapters():
    script = """
import sys
from jym_structural.core import CapacityValue, DemandCheck, demand_ratio
CapacityValue(component='p', value=1, unit='kN', limit_state='manual')
assert not any(name.startswith('jym_structural.adapters') for name in sys.modules)
"""
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)
