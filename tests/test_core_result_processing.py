import itertools
import json
import math
import subprocess
import sys

import pytest
from pydantic import ValidationError

from jym_structural.core import (
    AnalysisResult,
    DemandCheck,
    ForceEnvelope,
    ForceExtreme,
    FrameForces,
    ResultUnits,
    absolute_extreme,
    component_envelope,
    component_extreme,
    demand_ratio,
)


def source(**changes):
    values = {
        "object_id": "member-01",
        "station": 6,
        "element_id": "element-2",
        "element_station": 1,
        "load_case": "beta",
        "step_type": "Step",
        "step_num": 2,
        "p": -18,
        "v2": 15,
        "v3": -12,
        "t": -4,
        "m2": -10,
        "m3": 100,
    }
    values.update(changes)
    return FrameForces(**values)


def analysis(rows):
    return AnalysisResult(
        member_id="member-01",
        forces=rows,
        units=ResultUnits(force="kip", length="ft"),
    )


@pytest.fixture
def result():
    return analysis(
        [
            source(
                load_case="gamma",
                station=3,
                element_id="element-1",
                element_station=3,
                step_type="Max",
                step_num=1,
                p=0,
                v2=30,
                v3=-2,
                t=0,
                m2=-30,
                m3=40,
            ),
            source(),
            source(
                load_case="alpha",
                station=0,
                element_id="element-1",
                element_station=0,
                step_type=None,
                step_num=0,
                p=15,
                v2=-8,
                v3=9,
                t=6,
                m2=20,
                m3=-100,
            ),
        ]
    )


@pytest.mark.parametrize(
    "component,kind,value,label",
    [
        ("p", "max", 15, "alpha"),
        ("p", "min", -18, "beta"),
        ("v2", "max", 30, "gamma"),
        ("v2", "min", -8, "alpha"),
        ("v3", "min", -12, "beta"),
        ("v3", "max", 9, "alpha"),
        ("t", "max", 6, "alpha"),
        ("t", "min", -4, "beta"),
    ],
)
def test_signed_component_extremes(result, component, kind, value, label):
    extreme = component_extreme(result, component, kind=kind)
    assert extreme.value == value
    assert extreme.source.load_case == label
    assert extreme.member_id == result.member_id
    assert extreme.component == component
    assert extreme.kind == kind


@pytest.mark.parametrize("component,minimum,maximum", [("m2", -30, 20), ("m3", -100, 100)])
def test_envelope_has_independent_real_source_rows(result, component, minimum, maximum):
    envelope = component_envelope(result, component)
    assert envelope.minimum.value == minimum
    assert envelope.maximum.value == maximum
    assert envelope.minimum.source in result.forces
    assert envelope.maximum.source in result.forces
    assert envelope.minimum.source != envelope.maximum.source


def test_full_provenance_and_units_preserved_without_reinterpreting_axes(result):
    extreme = component_extreme(result, "p", kind="min")
    assert extreme.source == source()
    assert extreme.source.station == 6
    assert extreme.source.element_station == 1
    assert extreme.source.element_id == "element-2"
    assert extreme.source.step_type == "Step"
    assert extreme.source.step_num == 2
    assert extreme.units == result.units
    assert extreme.unit == "kip"
    moment = component_extreme(result, "m3", kind="max")
    assert moment.unit == "kip*ft"
    assert moment.units.length == "ft"
    assert moment.source.v2 == 15
    assert moment.source.v3 == -12
    assert moment.source.m2 == -10
    assert moment.source.m3 == 100


@pytest.mark.parametrize("component,value", [("t", 6), ("p", -18)])
def test_absolute_extreme_preserves_sign(result, component, value):
    extreme = absolute_extreme(result, component)
    assert extreme.value == value
    assert extreme.kind == "absolute"


def test_absolute_equal_magnitudes_choose_negative_before_provenance():
    positive = source(load_case="a", p=100)
    negative = source(load_case="z", p=-100)
    for rows in ([positive, negative], [negative, positive]):
        assert absolute_extreme(analysis(rows), "p").source == negative


@pytest.mark.parametrize("kind", ["min", "max"])
def test_equal_values_use_provenance_not_input_order(kind):
    a, b = source(load_case="a", p=100), source(load_case="b", p=100)
    for rows in ([b, a], [a, b]):
        assert component_extreme(analysis(rows), "p", kind=kind).source == a


@pytest.mark.parametrize(
    "earlier,later",
    [
        ({"step_type": None}, {"step_type": ""}),
        ({"step_type": "A"}, {"step_type": "B"}),
        ({"step_num": 1}, {"step_num": 2}),
        ({"station": 1}, {"station": 2}),
        ({"element_id": "e1"}, {"element_id": "e2"}),
        ({"element_station": 1}, {"element_station": 2}),
    ],
)
def test_provenance_tiebreak_fields(earlier, later):
    first, second = source(**earlier), source(**later)
    assert component_extreme(analysis([second, first]), "p", kind="max").source == first


def test_residual_ties_with_different_other_forces_are_stable():
    a, b = source(v2=1), source(v2=2)
    assert component_extreme(analysis([a, b]), "p", kind="max") == component_extreme(
        analysis([b, a]),
        "p",
        kind="max",
    )


def test_signed_zero_ties_are_stable():
    plus, minus = source(p=0.0), source(p=-0.0)
    a = absolute_extreme(analysis([plus, minus]), "p")
    b = absolute_extreme(analysis([minus, plus]), "p")
    assert a.model_dump_json() == b.model_dump_json()
    assert math.copysign(1, a.value) == -1


def test_all_permutations_produce_identical_outputs(result):
    expected = component_envelope(result, "m3").model_dump_json()
    expected_absolute = absolute_extreme(result, "m3").model_dump_json()
    for rows in itertools.permutations(result.forces):
        shuffled = analysis(list(rows))
        assert component_envelope(shuffled, "m3").model_dump_json() == expected
        assert absolute_extreme(shuffled, "m3").model_dump_json() == expected_absolute


@pytest.mark.parametrize("operation", [component_envelope, absolute_extreme])
def test_empty_input_rejected(operation):
    with pytest.raises(ValueError, match="must not be empty"):
        operation(analysis([]), "p")


@pytest.mark.parametrize("component", ["u1", "P", "shell", "", None])
def test_unsupported_component(result, component):
    with pytest.raises(ValueError, match="Unsupported force component"):
        component_envelope(result, component)


def test_invalid_kind(result):
    with pytest.raises(ValueError, match="Unsupported component extreme kind"):
        component_extreme(result, "p", kind="absolute")


@pytest.mark.parametrize(
    "field", ["p", "object_id", "station", "load_case", "element_id", "element_station", "step_num"]
)
def test_any_incomplete_row_fails_even_if_it_would_not_control(result, field):
    setattr(result.forces[0], field, None)
    with pytest.raises(ValidationError, match="Source " + field):
        component_extreme(result, "p", kind="min")


def test_null_step_type_is_legitimate(result):
    assert component_extreme(result, "p", kind="max").source.step_type is None


def test_unrequested_missing_component_remains_explicit():
    extreme = component_extreme(analysis([source(m3=None)]), "p", kind="max")
    assert extreme.source.m3 is None
    with pytest.raises(ValidationError, match="Source m3 is required"):
        component_envelope(analysis([source(m3=None)]), "m3")


def test_mixed_member_ids_fail(result):
    result.forces[0].object_id = "different-member"
    with pytest.raises(ValidationError, match="must match member_id"):
        absolute_extreme(result, "p")


def test_units_absent_fail(result):
    result.units = None
    with pytest.raises(ValueError, match="units is required"):
        component_envelope(result, "p")


def test_blank_units_fail(result):
    result.units.force = " "
    with pytest.raises(ValidationError, match="units must be nonblank"):
        absolute_extreme(result, "p")


def test_nonfinite_values_edited_after_construction_are_revalidated(result):
    result.forces[0].p = float("nan")
    with pytest.raises(ValidationError, match="finite number"):
        absolute_extreme(result, "p")


def test_inputs_unchanged_and_no_snapshot_aliasing(result):
    before = result.model_dump_json()
    identities = [id(row) for row in result.forces]
    minimum = component_extreme(result, "p", kind="min")
    envelope = component_envelope(result, "m3")
    absolute = absolute_extreme(result, "p")
    check = demand_ratio(absolute, 20)
    assert result.model_dump_json() == before
    assert [id(row) for row in result.forces] == identities
    minimum.source.p = -99
    assert result.model_dump_json() == before
    result.forces[1].p = 45
    result.units.force = "other"
    assert check.demand.value == -18
    assert check.demand.unit == "kip"
    assert envelope.maximum.value == 100


def test_new_models_round_trip_json(result):
    extreme = component_extreme(result, "p", kind="max")
    envelope = component_envelope(result, "m2")
    check = demand_ratio(extreme, 20)
    for value, model in ((extreme, ForceExtreme), (envelope, ForceEnvelope), (check, DemandCheck)):
        assert model.model_validate_json(value.model_dump_json()) == value


@pytest.mark.parametrize(
    "field,value",
    [
        ("component", "m3"),
        ("kind", "absolute"),
        ("member_id", "other"),
        ("units", {"force": "N", "length": "mm"}),
    ],
)
def test_envelope_rejects_inconsistent_extremes(result, field, value):
    minimum = component_extreme(result, "p", kind="min")
    maximum = component_extreme(result, "p", kind="max")
    bad = maximum.model_dump(round_trip=True)
    bad[field] = value
    if field == "member_id":
        bad["source"]["object_id"] = value
    with pytest.raises(ValidationError, match="Envelope"):
        ForceEnvelope(component="p", minimum=minimum, maximum=bad)


def test_envelope_detaches_supplied_extremes(result):
    minimum = component_extreme(result, "p", kind="min")
    maximum = component_extreme(result, "p", kind="max")
    envelope = ForceEnvelope(component="p", minimum=minimum, maximum=maximum)
    minimum.source.p = -999
    maximum.units.force = "other"
    assert envelope.minimum.value == -18
    assert envelope.maximum.unit == "kip"


@pytest.mark.parametrize(
    "demand,capacity,ratio,passes",
    [
        (15, 20, 0.75, True),
        (20, 20, 1, True),
        (25, 20, 1.25, False),
        (-15, 20, 0.75, True),
        (0, 20, 0, True),
    ],
)
def test_demand_check(demand, capacity, ratio, passes):
    extreme = absolute_extreme(analysis([source(p=demand)]), "p")
    check = demand_ratio(extreme, capacity)
    assert check.ratio == ratio
    assert check.passes is passes
    assert check.demand == extreme
    assert check.demand.units == ResultUnits(force="kip", length="ft")
    assert check.demand.source == source(p=demand)
    extreme.source.p = 999
    assert check.ratio == ratio


@pytest.mark.parametrize("capacity", [0, -1, float("nan"), float("inf"), "20", True])
def test_invalid_capacity(result, capacity):
    with pytest.raises(ValidationError):
        demand_ratio(absolute_extreme(result, "p"), capacity)


def test_ratio_overflow_rejected():
    with pytest.raises(ValidationError, match="ratio must be finite"):
        demand_ratio(absolute_extreme(analysis([source(p=1e308)]), "p"), 5e-324)


def test_core_import_and_processing_do_not_load_any_adapter():
    script = """
import json
import sys
from jym_structural.core import AnalysisResult, FrameForces, ResultUnits, absolute_extreme
r = AnalysisResult(member_id='n', units=ResultUnits(force='F', length='L'), forces=[
    FrameForces(object_id='n', station=0, element_id='e', element_station=0,
                load_case='neutral', step_num=0, p=1)])
assert absolute_extreme(r, 'p').value == 1
print(json.dumps([name for name in sys.modules if name.startswith('jym_structural.adapters')]))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script], check=True, text=True, capture_output=True
    )
    assert json.loads(completed.stdout) == []
