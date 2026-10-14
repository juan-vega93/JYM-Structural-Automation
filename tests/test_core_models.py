from jym_structural.core.models import FrameForces, Member


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
