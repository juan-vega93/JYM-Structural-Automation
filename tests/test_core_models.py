import pytest
from pydantic import ValidationError

from jym_structural.core.models import AnalysisResult, FrameForces, Member, ResultUnits


def test_member_serializes_to_stable_json_shape():
    member = Member(id="1", name="B1", section="W12x65", length=6.0)
    data = member.model_dump()
    assert data["name"] == "B1"
    assert data["section"] == "W12x65"
    assert data["length"] == 6.0


def test_frame_forces_use_structural_axes():
    result = FrameForces(v2=7.82, v3=0.57, t=0.12, m2=1.19, m3=16.35)
    assert result.m3 == 16.35
    assert result.v2 == 7.82


def test_force_row_preserves_object_and_element_provenance():
    row = FrameForces(
        object_id="001",
        station=6,
        element_id="001-2",
        element_station=1,
        load_case="combination",
        step_type="Max",
        step_num=0,
        p=-12.3456789,
    )
    result = AnalysisResult(
        member_id="001", forces=[row], units=ResultUnits(force="kip", length="ft")
    )
    assert result.units.moment == "kip*ft"
    assert row.station != row.element_station
    assert row.p == -12.3456789
    assert AnalysisResult.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize(
    "field,value",
    [
        ("station", float("nan")),
        ("element_station", float("inf")),
        ("step_num", float("-inf")),
        ("p", float("nan")),
    ],
)
def test_force_row_rejects_nonfinite_numbers_in_core(field, value):
    with pytest.raises(ValidationError, match="finite number"):
        FrameForces(**{field: value})
