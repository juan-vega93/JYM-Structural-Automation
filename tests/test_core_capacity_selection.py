import itertools
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
    governing_capacity,
)


def capacity(**changes):
    values = {"component": "p", "value": 100, "unit": "N", "limit_state": "manual"}
    values.update(changes)
    return CapacityValue(**values)


@pytest.mark.parametrize("count", [1, 2, 3])
def test_minimum_original_instance_and_all_permutations(count):
    candidates = [capacity(value=n) for n in range(1, count + 1)]
    for order in itertools.permutations(candidates):
        assert governing_capacity(order) is candidates[0]


@pytest.mark.parametrize("container", [list, tuple, iter])
def test_empty_input(container):
    with pytest.raises(ValueError, match="At least one capacity is required"):
        governing_capacity(container([]))


def test_generator_consumed_once_and_validates_non_controlling_items():
    visited = []
    low, high = capacity(value=1), capacity(value=100)

    def candidates():
        for value in (high, low, high):
            visited.append(value)
            yield value

    assert governing_capacity(candidates()) is low
    assert visited == [high, low, high]
    with pytest.raises(TypeError, match="CapacityValue"):
        governing_capacity(item for item in [low, {}])


@pytest.mark.parametrize("component", ["p", "v2", "v3", "t", "m2", "m3"])
def test_all_neutral_components(component):
    unit = "N" if component in ("p", "v2", "v3") else "N*mm"
    low = capacity(component=component, unit=unit, value=1)
    assert governing_capacity([capacity(component=component, unit=unit), low]) is low


@pytest.mark.parametrize(
    "field,first,second",
    [
        ("component", "p", "v2"),
        ("unit", "N", "kN"),
        ("unit", "N", "N "),
        ("unit", "N*mm", "N·mm"),
        ("member_id", "12", "15"),
        ("member_id", None, "12"),
        ("section_name", "S", "T"),
        ("section_name", None, "S"),
        ("material_name", "steel", "Steel"),
        ("material_name", None, "steel"),
        ("member_id", "12", "12 "),
        ("section_name", "S", "S "),
        ("material_name", "steel", "steel "),
    ],
)
def test_strict_compatibility_fields(field, first, second):
    a, b = capacity(**{field: first}), capacity(**{field: second})
    for order in ([a, b], [b, a]):
        with pytest.raises(ValueError, match=field):
            governing_capacity(order)


@pytest.mark.parametrize("reference", [None, " exact ID "])
def test_all_optional_identity_fields_equal(reference):
    fields = {name: reference for name in ("member_id", "section_name", "material_name")}
    a, b = capacity(**fields), capacity(value=50, **fields)
    assert governing_capacity([a, b]) is b


def test_sources_and_limit_states_can_differ_and_winner_preserves_them():
    a = capacity(limit_state="yield", source=PropertySource(kind="manual", name="A"))
    b = capacity(value=50, limit_state="buckling", source=PropertySource(kind="solver", name="B"))
    assert governing_capacity([a, b]) is b
    assert b.source.name == "B"
    assert b.limit_state == "buckling"


def test_limit_state_tie_break_two_and_three_way():
    a, b, c = [capacity(limit_state=state) for state in ("z_state", "a_state", "b_state")]
    for candidates in ([a, b], [a, b, c]):
        for order in itertools.permutations(candidates):
            assert governing_capacity(order) is b


def test_source_tie_break_is_canonical_data_not_order():
    candidates = [
        capacity(source=source)
        for source in (
            None,
            PropertySource(kind="manual", name="z"),
            PropertySource(kind="manual", name="a"),
            PropertySource(kind="imported"),
        )
    ]
    # JSON null sorts before object JSON; among objects imported precedes manual.
    for order in itertools.permutations(candidates):
        assert governing_capacity(order) is candidates[0]
    for order in itertools.permutations(candidates[1:]):
        assert governing_capacity(order) is candidates[3]


@pytest.mark.parametrize("field", ["name", "version"])
def test_source_optional_fields_break_remaining_ties(field):
    a = capacity(source=PropertySource(kind="manual", **{field: "a"}))
    z = capacity(source=PropertySource(kind="manual", **{field: "z"}))
    assert governing_capacity([z, a]) is a
    assert governing_capacity([a, z]) is a


def test_exact_duplicates_are_accepted_as_logically_equivalent():
    original = capacity()
    duplicate = original.model_copy(deep=True)
    assert governing_capacity([original, original]) is original
    for order in ([original, duplicate], [duplicate, original]):
        chosen = governing_capacity(order)
        assert chosen is original or chosen is duplicate
        assert chosen == original


@pytest.mark.parametrize("invalid", [{"value": 1}, None, 1, "capacity"])
def test_non_capacity_elements_rejected(invalid):
    with pytest.raises(TypeError, match="Each capacity must be a CapacityValue"):
        governing_capacity([invalid])


@pytest.mark.parametrize(
    "field,value",
    [
        ("value", 0),
        ("value", -1),
        ("value", float("nan")),
        ("value", float("inf")),
        ("unit", ""),
        ("limit_state", ""),
        ("member_id", " "),
        ("component", "invalid"),
        ("source", PropertySource(kind="manual").model_copy(update={"name": ""})),
    ],
)
def test_revalidates_all_unchecked_copies(field, value):
    invalid = capacity().model_copy(update={field: value})
    with pytest.raises(ValidationError):
        governing_capacity([capacity(value=1), invalid])


def test_no_input_mutation_or_in_place_sort_and_frozen_roundtrip():
    a, b, c = capacity(value=300), capacity(value=100), capacity(value=200)
    values = [a, b, c]
    before = [value.model_dump_json() for value in values]
    assert governing_capacity(values) is b
    assert values[0] is a and values[1] is b and values[2] is c
    assert before == [value.model_dump_json() for value in values]
    assert CapacityValue.model_validate_json(b.model_dump_json()) == b
    with pytest.raises(ValidationError, match="frozen"):
        b.value = 1


def test_synthetic_axial_candidates_to_demand_check():
    references = {"member_id": "12", "section_name": "S", "material_name": "M"}
    yielding = capacity(value=2_500_000, limit_state="steel_axial_yielding", **references)
    euler = capacity(value=1_800_000, limit_state="steel_euler_buckling", **references)
    governing = governing_capacity([yielding, euler])
    assert governing is euler
    demand = ForceExtreme(
        member_id="12",
        component="p",
        kind="absolute",
        source=FrameForces(
            object_id="12",
            station=0,
            element_id="e",
            element_station=0,
            load_case="synthetic",
            step_num=0,
            p=-900_000,
        ),
        units=ResultUnits(force="N", length="mm"),
    )
    check = demand_ratio(demand, governing)
    assert check.ratio == 0.5 and check.passes
    assert check.capacity.limit_state == "steel_euler_buckling"
    assert DemandCheck.model_validate_json(check.model_dump_json()) == check


def test_synthetic_flexural_candidates_no_future_calculator_required():
    yielding = capacity(
        component="m3", unit="N*mm", value=200_000_000, limit_state="steel_flexural_yielding"
    )
    future = capacity(component="m3", unit="N*mm", value=150_000_000, limit_state="future_ltb")
    assert governing_capacity([yielding, future]) is future


def test_core_selection_without_design_adapters_comtypes_or_calculator_calls():
    script = """
import sys
from jym_structural.core import CapacityValue, governing_capacity
a = CapacityValue(component='p', value=2, unit='N', limit_state='a')
b = CapacityValue(component='p', value=1, unit='N', limit_state='b')
assert governing_capacity([a, b]) is b
assert not any(n.startswith(('jym_structural.design', 'jym_structural.adapters', 'comtypes'))
               for n in sys.modules)
"""
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)
