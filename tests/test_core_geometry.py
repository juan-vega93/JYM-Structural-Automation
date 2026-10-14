import pytest
from pydantic import ValidationError

from jym_structural.core import Member, ModelInfo, Node, Point3D, Section, StructuralModel


@pytest.fixture
def geometry_data():
    return {
        "model_info": {"software": "neutral-test", "units": "source units"},
        "length_unit": "ft",
        "nodes": [
            {"id": "01", "position": {"x": 0.0, "y": 0.0, "z": 0.0}},
            {"id": "1", "position": {"x": 3.0, "y": 4.0, "z": 12.0}},
        ],
        "sections": [{"name": "S 01", "material": "steel"}],
        "members": [
            {
                "id": "001",
                "name": "member",
                "start_node": "01",
                "end_node": "1",
                "section": "S 01",
                "length": 13.0,
            }
        ],
    }


def test_neutral_geometry_keeps_identifiers_units_and_round_trips(geometry_data):
    model = StructuralModel.model_validate(geometry_data)
    assert isinstance(model.model_info, ModelInfo)
    assert isinstance(model.nodes[0], Node)
    assert isinstance(model.nodes[0].position, Point3D)
    assert isinstance(model.sections[0], Section)
    assert isinstance(model.members[0], Member)
    assert model.nodes[1].position == Point3D(x=3, y=4, z=12)
    assert model.length_unit == "ft"
    assert model.members[0].start_node == "01"
    assert model.members[0].id == "001"
    assert model.members[0].section == "S 01"
    assert StructuralModel.model_validate_json(model.model_dump_json()) == model


@pytest.mark.parametrize(
    "collection,label",
    [
        ("nodes", "node"),
        ("members", "member"),
        ("sections", "section"),
    ],
)
def test_duplicates_are_rejected_even_when_data_are_identical(geometry_data, collection, label):
    geometry_data[collection].append(geometry_data[collection][0].copy())
    with pytest.raises(ValidationError, match=f"Duplicate {label} identifier"):
        StructuralModel.model_validate(geometry_data)


@pytest.mark.parametrize("endpoint", ["start_node", "end_node"])
@pytest.mark.parametrize("missing", ["missing", None])
def test_every_member_endpoint_must_reference_a_node(geometry_data, endpoint, missing):
    geometry_data["members"][0][endpoint] = missing
    with pytest.raises(ValidationError, match=f"{endpoint} references missing node"):
        StructuralModel.model_validate(geometry_data)


def test_unknown_section_rejected(geometry_data):
    geometry_data["members"][0]["section"] = "missing"
    with pytest.raises(ValidationError, match="references missing section"):
        StructuralModel.model_validate(geometry_data)


def test_unassigned_section_is_allowed(geometry_data):
    geometry_data["members"][0]["section"] = None
    geometry_data["sections"] = []
    assert StructuralModel.model_validate(geometry_data).members[0].section is None


@pytest.mark.parametrize("axis", ["x", "y", "z"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_coordinates_rejected_by_core(geometry_data, axis, value):
    geometry_data["nodes"][0]["position"][axis] = value
    with pytest.raises(ValidationError, match="finite number"):
        StructuralModel.model_validate(geometry_data)
    with pytest.raises(ValidationError, match="finite number"):
        Point3D(**{"x": 0, "y": 0, "z": 0, axis: value})


def test_empty_model_and_independent_collections():
    info = ModelInfo(software="neutral-test")
    first = StructuralModel(model_info=info, length_unit="mm")
    second = StructuralModel(model_info=info, length_unit="mm")
    assert first.nodes == first.members == first.sections == []
    first.nodes.append(Node(id="isolated", position=Point3D(x=0, y=0, z=0)))
    assert second.nodes == []


@pytest.mark.parametrize("unit", [None, "", " "])
def test_length_unit_is_required_and_nonblank(unit):
    with pytest.raises(ValidationError):
        StructuralModel(model_info=ModelInfo(software="neutral-test"), length_unit=unit)
