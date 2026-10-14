import copy
import json
from unittest.mock import Mock, call

import pytest

from jym_structural.adapters.sap2000 import ComSap2000Gateway, Sap2000Error, Sap2000ResultsReader
from jym_structural.adapters.sap2000 import __main__ as diagnostic
from jym_structural.core import AnalysisResult, FrameForces, ResultUnits

# Verified comtypes order, deliberately different object/element stations.
FIELDS = (
    "Obj",
    "ObjSta",
    "Elm",
    "ElmSta",
    "LoadCase",
    "StepType",
    "StepNum",
    "P",
    "V2",
    "V3",
    "T",
    "M2",
    "M3",
)
ROWS = [
    ("12", 6.0, "12-2", 1.0, "COMB", "Max", 0.0, 11, 12, 13, 14, 15, 16),
    ("12", 2.0, "12-1", 2.0, "CASE", "Step", 2.0, 21, 22, 23, 24, 25, 26),
    ("12", 1.0, "12-1", 1.0, "CASE", "Step", 1.0, 31, 32, 33, 34, 35, 36),
    ("12", 0.0, "12-1", 0.0, "STATIC", None, 0.0, -41, -42, -43, -44, -45, -46),
]


def response(rows=ROWS):
    return [len(rows), *[list(column) for column in zip(*rows, strict=True)], 0]


@pytest.fixture
def results_connection():
    model = Mock(
        spec=[
            "GetVersion",
            "GetModelFilename",
            "GetPresentUnits",
            "Results",
            "Analyze",
            "File",
            "SetPresentUnits",
            "SetModelIsLocked",
        ]
    )
    model.GetVersion.return_value = ("26.2.0", 26.2, 0)
    model.GetModelFilename.return_value = r"C:\Test\analyzed.sdb"
    model.GetPresentUnits.return_value = 8
    model.Results = Mock(spec=["FrameForce", "Setup"])
    model.Results.FrameForce.return_value = response()
    model.Results.Setup = Mock(
        spec=[
            "GetCaseSelectedForOutput",
            "GetComboSelectedForOutput",
            "DeselectAllCasesAndCombosForOutput",
            "SetCaseSelectedForOutput",
            "SetComboSelectedForOutput",
        ]
    )
    model.Analyze = Mock(spec=["RunAnalysis"])
    model.File = Mock(spec=["Save"])
    attach = Mock(return_value=Mock(SapModel=model))
    gateway = ComSap2000Gateway(attach=attach)
    gateway.connect_to_running_instance()
    model.reset_mock()
    return gateway, model, attach


def test_connection_is_required_without_reconnecting():
    attach = Mock()
    with pytest.raises(Sap2000Error, match="Connect to a running"):
        ComSap2000Gateway(attach=attach).get_member_results("12")
    attach.assert_not_called()


def test_results_provenance_steps_components_units_and_read_only_boundary(results_connection):
    gateway, model, attach = results_connection
    reader: Sap2000ResultsReader = gateway
    result = reader.get_member_results("12")
    assert isinstance(result, AnalysisResult)
    assert all(isinstance(row, FrameForces) for row in result.forces)
    assert result.member_id == "12"
    assert result.units == ResultUnits(force="kgf", length="m")
    assert result.units.moment == "kgf*m"
    assert [row.load_case for row in result.forces] == ["CASE", "CASE", "COMB", "STATIC"]
    expected_order = [2, 1, 0, 3]
    for actual, index in zip(result.forces, expected_order, strict=True):
        expected = ROWS[index]
        assert (
            actual.object_id,
            actual.station,
            actual.element_id,
            actual.element_station,
            actual.load_case,
            actual.step_type,
            actual.step_num,
            actual.p,
            actual.v2,
            actual.v3,
            actual.t,
            actual.m2,
            actual.m3,
        ) == expected
    assert result.forces[2].station == 6.0
    assert result.forces[2].element_station == 1.0
    assert result.forces[-1].step_type is None
    assert AnalysisResult.model_validate_json(result.model_dump_json()) == result
    assert model.mock_calls == [
        call.GetVersion(),
        call.GetModelFilename(True),
        call.GetPresentUnits(),
        call.Results.FrameForce(Name="12", ItemTypeElm=0),
        call.GetVersion(),
        call.GetModelFilename(True),
        call.GetPresentUnits(),
    ]
    model.Analyze.RunAnalysis.assert_not_called()
    model.File.Save.assert_not_called()
    model.SetPresentUnits.assert_not_called()
    model.SetModelIsLocked.assert_not_called()
    assert model.Results.Setup.mock_calls == []
    attach.assert_called_once_with()


def test_deterministic_order_and_no_row_deduplication(results_connection):
    gateway, model, _ = results_connection
    rows = [*ROWS, ROWS[0], (*ROWS[0][:7], -10, *ROWS[0][8:])]
    model.Results.FrameForce.return_value = response(rows)
    first = gateway.get_member_results("12")
    model.Results.FrameForce.return_value = response(rows[::-1])
    assert gateway.get_member_results("12") == first
    assert len(first.forces) == len(rows)


def test_present_units_not_converted(results_connection):
    gateway, model, _ = results_connection
    model.GetPresentUnits.return_value = 4
    result = gateway.get_member_results("12")
    assert result.units.model_dump() == {"force": "kip", "length": "ft", "moment": "kip*ft"}
    assert result.forces[0].p == 31
    assert result.forces[0].station == 1


@pytest.mark.parametrize("field", FIELDS)
def test_every_parallel_array_must_match_count(results_connection, field):
    gateway, model, _ = results_connection
    bad = response()
    bad[1 + FIELDS.index(field)].pop()
    model.Results.FrameForce.return_value = bad
    with pytest.raises(Sap2000Error, match=field + " length"):
        gateway.get_member_results("12")


@pytest.mark.parametrize("count", [-1, True, 4.0, "4", 5])
def test_invalid_or_inconsistent_number_results(results_connection, count):
    gateway, model, _ = results_connection
    bad = response()
    bad[0] = count
    model.Results.FrameForce.return_value = bad
    with pytest.raises(Sap2000Error, match="NumberResults"):
        gateway.get_member_results("12")


@pytest.mark.parametrize("field", ["ObjSta", "ElmSta", "StepNum", "P", "V2", "V3", "T", "M2", "M3"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "3", True])
def test_all_numeric_arrays_must_be_finite_numbers(results_connection, field, value):
    gateway, model, _ = results_connection
    bad = response()
    bad[1 + FIELDS.index(field)][0] = value
    model.Results.FrameForce.return_value = bad
    with pytest.raises(Sap2000Error, match="invalid " + field):
        gateway.get_member_results("12")


@pytest.mark.parametrize(
    "field,value",
    [
        ("Obj", "99"),
        ("Obj", 12),
        ("Elm", None),
        ("Elm", ""),
        ("LoadCase", 3),
        ("LoadCase", ""),
        ("StepType", 2),
    ],
)
def test_invalid_ids_and_strings_fail(results_connection, field, value):
    gateway, model, _ = results_connection
    bad = response()
    bad[1 + FIELDS.index(field)][0] = value
    model.Results.FrameForce.return_value = bad
    with pytest.raises(Sap2000Error, match="Results.FrameForce"):
        gateway.get_member_results("12")


@pytest.mark.parametrize("code", [1, -1, 7])
def test_csi_error_includes_operation_member_and_code(results_connection, code):
    gateway, model, _ = results_connection
    bad = response()
    bad[-1] = code
    model.Results.FrameForce.return_value = bad
    with pytest.raises(Sap2000Error, match=rf"Results.FrameForce\('12'\).*CSI return code {code}"):
        gateway.get_member_results("12")
    model.Results.FrameForce.assert_called_once_with(Name="12", ItemTypeElm=0)


def test_com_error_preserves_cause(results_connection):
    gateway, model, attach = results_connection
    failure = OSError("COM failure")
    model.Results.FrameForce.side_effect = failure
    with pytest.raises(Sap2000Error, match="FrameForce.*12.*COM query failed") as raised:
        gateway.get_member_results("12")
    assert raised.value.__cause__ is failure
    attach.assert_called_once_with()


@pytest.mark.parametrize("empty", [None, (), []])
def test_zero_rows_is_explicit_no_results_without_analysis(results_connection, empty):
    gateway, model, _ = results_connection
    model.Results.FrameForce.return_value = [0, *[copy.copy(empty) for _ in FIELDS], 0]
    with pytest.raises(Sap2000Error, match="no results for the current output selection"):
        gateway.get_member_results("12")
    model.Analyze.RunAnalysis.assert_not_called()
    assert model.Results.Setup.mock_calls == []


@pytest.mark.parametrize("bad", [[], [0], None, [0, *[() for _ in FIELDS], 0, 0]])
def test_unverified_response_shape_rejected(results_connection, bad):
    gateway, model, _ = results_connection
    model.Results.FrameForce.return_value = bad
    with pytest.raises(Sap2000Error, match="unexpected COM response shape"):
        gateway.get_member_results("12")


def test_units_changed_during_read_rejected(results_connection):
    gateway, model, _ = results_connection
    model.GetPresentUnits.side_effect = [8, 4]
    with pytest.raises(Sap2000Error, match="present units changed"):
        gateway.get_member_results("12")


@pytest.mark.parametrize("member", ["", " ", None, 12])
def test_invalid_member_input(results_connection, member):
    gateway, model, _ = results_connection
    with pytest.raises(Sap2000Error, match="nonempty member ID"):
        gateway.get_member_results(member)
    model.Results.FrameForce.assert_not_called()


def test_cli_reads_only_requested_frame(results_connection, monkeypatch, capsys):
    gateway, model, _ = results_connection
    monkeypatch.setattr(diagnostic, "ComSap2000Gateway", lambda: gateway)
    assert diagnostic.main(["--frame-results", "12"]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)["member_id"] == "12"
    assert output.err == ""
    model.Results.FrameForce.assert_called_once_with(Name="12", ItemTypeElm=0)
    model.Analyze.RunAnalysis.assert_not_called()
    assert model.Results.Setup.mock_calls == []


def test_cli_failure_no_partial_json(results_connection, monkeypatch, capsys):
    gateway, model, _ = results_connection
    model.Results.FrameForce.return_value[-1] = 9
    monkeypatch.setattr(diagnostic, "ComSap2000Gateway", lambda: gateway)
    assert diagnostic.main(["--frame-results", "12"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "CSI return code 9" in output.err


@pytest.mark.parametrize("other", ["--run-analysis", "--inventory"])
def test_cli_modes_cannot_combine(monkeypatch, capsys, other):
    factory = Mock()
    monkeypatch.setattr(diagnostic, "ComSap2000Gateway", factory)
    with pytest.raises(SystemExit) as error:
        diagnostic.main(["--frame-results", "12", other])
    assert error.value.code == 2
    factory.assert_not_called()
    assert capsys.readouterr().out == ""
