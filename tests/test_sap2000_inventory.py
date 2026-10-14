import json
from unittest.mock import Mock, call

import pytest

from jym_structural.adapters.sap2000 import (
    ComSap2000Gateway,
    Sap2000Error,
    Sap2000ModelReader,
)
from jym_structural.adapters.sap2000 import __main__ as diagnostic
from jym_structural.core.models import Member, Section


@pytest.fixture
def inventory():
    frame = Mock(spec=["GetNameList", "GetPoints", "GetSection"])
    frame.GetNameList.return_value = [2, ("20", "10"), 0]
    frame.GetPoints.side_effect = lambda *, Name: {
        "10": ("I", "J", 0),
        "20": ("J", "K", 0),
    }[Name]
    frame.GetSection.side_effect = lambda *, Name: {
        "10": ("W12", "AUTO", 0),
        "20": ("W8", "", 0),
    }[Name]
    prop = Mock(spec=["GetNameList", "GetMaterial"])
    prop.GetNameList.return_value = (2, ["W8", "W12"], 0)
    prop.GetMaterial.side_effect = lambda *, Name: {"W12": ("A992", 0), "W8": ("A36", 0)}[Name]
    point = Mock(spec=["GetCoordCartesian"])

    def xyz(*, Name, CSys):
        assert CSys == "Global"
        return {"I": (0.0, 0.0, 0.0, 0), "J": (3.0, 4.0, 12.0, 0), "K": (3.0, 4.0, 14.0, 0)}[Name]

    point.GetCoordCartesian.side_effect = xyz
    model = Mock(
        spec=[
            "GetVersion",
            "GetModelFilename",
            "GetPresentUnits",
            "FrameObj",
            "PropFrame",
            "PointObj",
        ]
    )
    model.GetVersion.return_value = ["26.2.0", 26.2, 0]
    model.GetModelFilename.return_value = r"C:\Models\frame.sdb"
    model.GetPresentUnits.return_value = 6
    model.FrameObj, model.PropFrame, model.PointObj = frame, prop, point
    adapter = ComSap2000Gateway(attach=lambda: Mock(SapModel=model))
    adapter.connect_to_running_instance()
    model.reset_mock()
    return adapter, model


def test_inventory_core_models_topology_material_and_geometric_length(inventory):
    adapter, model = inventory
    reader: Sap2000ModelReader = adapter
    sections = reader.list_sections()
    members = reader.list_members()
    assert all(isinstance(section, Section) for section in sections)
    assert all(isinstance(member, Member) for member in members)
    assert [section.name for section in sections] == ["W12", "W8"]
    assert [member.model_dump() for member in members] == [
        {
            "id": "10",
            "name": "10",
            "section": "W12",
            "start_node": "I",
            "end_node": "J",
            "length": 13.0,
        },
        {
            "id": "20",
            "name": "20",
            "section": "W8",
            "start_node": "J",
            "end_node": "K",
            "length": 2.0,
        },
    ]
    materials = {section.name: section.material for section in sections}
    assert materials[members[0].section] == "A992"
    assert materials[members[1].section] == "A36"
    assert model.PointObj.GetCoordCartesian.call_args_list == [
        call(Name="I", CSys="Global"),
        call(Name="J", CSys="Global"),
        call(Name="K", CSys="Global"),
    ]
    # The next inventory must read fresh coordinates, not reuse a stale COM snapshot.
    model.PointObj.GetCoordCartesian.reset_mock()
    assert reader.list_members() == members
    assert model.PointObj.GetCoordCartesian.call_count == 3


@pytest.mark.parametrize("empty", [None, (), []])
def test_empty_model(inventory, empty):
    adapter, model = inventory
    model.FrameObj.GetNameList.return_value = (0, empty, 0)
    model.PropFrame.GetNameList.return_value = (0, empty, 0)
    assert adapter.list_sections() == []
    assert adapter.list_members() == []
    model.FrameObj.GetPoints.assert_not_called()
    model.FrameObj.GetSection.assert_not_called()
    model.PropFrame.GetMaterial.assert_not_called()
    model.PointObj.GetCoordCartesian.assert_not_called()


@pytest.mark.parametrize("method", ["list_sections", "list_members"])
def test_inventory_requires_explicit_connection(method):
    attach = Mock()
    adapter = ComSap2000Gateway(attach=attach)
    with pytest.raises(Sap2000Error, match="Connect to a running"):
        getattr(adapter, method)()
    attach.assert_not_called()


@pytest.mark.parametrize(
    "owner,method,output,reader",
    [
        ("FrameObj", "GetNameList", (0, (), 4), "list_members"),
        ("PropFrame", "GetNameList", (0, (), 4), "list_sections"),
        ("FrameObj", "GetPoints", ("I", "J", 4), "list_members"),
        ("FrameObj", "GetSection", ("W12", "", 4), "list_members"),
        ("PropFrame", "GetMaterial", ("A992", 4), "list_sections"),
        ("PointObj", "GetCoordCartesian", (0.0, 0.0, 0.0, 4), "list_members"),
    ],
)
def test_every_csi_status_is_checked(inventory, owner, method, output, reader):
    adapter, model = inventory
    operation = getattr(getattr(model, owner), method)
    operation.side_effect = None
    operation.return_value = output
    with pytest.raises(Sap2000Error, match=rf"{owner}.{method}.*CSI return code 4"):
        getattr(adapter, reader)()


@pytest.mark.parametrize(
    "output",
    [
        (2, ["10"], 0),
        (1, ["10", "20"], 0),
        (2, ["10", "10"], 0),
        (1, [""], 0),
        (1, [5], 0),
        (-1, [], 0),
        (0, [], 0, 0),
        (0, 2, ["10", "20"]),  # Reject unverified return-code-first order.
    ],
)
def test_invalid_or_reordered_arrays_fail_explicitly(inventory, output):
    adapter, model = inventory
    model.FrameObj.GetNameList.return_value = output
    with pytest.raises(Sap2000Error, match="FrameObj.GetNameList"):
        adapter.list_members()


@pytest.mark.parametrize("xyz", [(float("nan"), 0, 0, 0), (0, float("inf"), 0, 0), ("3", 4, 12, 0)])
def test_invalid_point_coordinates(inventory, xyz):
    adapter, model = inventory
    model.PointObj.GetCoordCartesian.side_effect = None
    model.PointObj.GetCoordCartesian.return_value = xyz
    with pytest.raises(Sap2000Error, match="invalid XYZ"):
        adapter.list_members()


def test_com_failure_preserves_cause(inventory):
    adapter, model = inventory
    model.FrameObj.GetNameList.side_effect = OSError("COM disconnected")
    with pytest.raises(Sap2000Error, match="FrameObj.GetNameList COM query failed") as error:
        adapter.list_members()
    assert isinstance(error.value.__cause__, OSError)


@pytest.mark.parametrize("endpoints", [("", "J", 0), ("I", None, 0)])
def test_invalid_endpoints_do_not_produce_topology(inventory, endpoints):
    adapter, model = inventory
    model.FrameObj.GetPoints.side_effect = None
    model.FrameObj.GetPoints.return_value = endpoints
    with pytest.raises(Sap2000Error, match="invalid endpoints"):
        adapter.list_members()
    model.PointObj.GetCoordCartesian.assert_not_called()


def test_missing_assignment_and_material_are_not_invented(inventory):
    adapter, model = inventory
    model.FrameObj.GetSection.side_effect = None
    model.FrameObj.GetSection.return_value = ("None", "", 0)
    model.PropFrame.GetMaterial.side_effect = None
    model.PropFrame.GetMaterial.return_value = ("", 0)
    assert all(member.section is None for member in adapter.list_members())
    assert all(section.material is None for section in adapter.list_sections())


def test_inventory_cli(inventory, monkeypatch, capsys):
    adapter, _ = inventory
    monkeypatch.setattr(diagnostic, "ComSap2000Gateway", lambda: adapter)
    assert diagnostic.main(["--inventory"]) == 0
    output = capsys.readouterr()
    data = json.loads(output.out)
    assert output.err == ""
    assert data["counts"] == {"sections": 2, "members": 2}
    assert data["members"][0]["length"] == 13.0
    assert data["sources"]["length_unit"] == "m"
    assert "derived" in data["sources"]["length"]


def test_inventory_cli_failure_has_no_partial_json(inventory, monkeypatch, capsys):
    adapter, model = inventory
    model.FrameObj.GetNameList.return_value = (0, (), 5)
    monkeypatch.setattr(diagnostic, "ComSap2000Gateway", lambda: adapter)
    assert diagnostic.main(["--inventory"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "CSI return code 5" in output.err
