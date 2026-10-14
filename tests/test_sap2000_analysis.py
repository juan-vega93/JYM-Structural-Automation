import json
from unittest.mock import Mock, call

import pytest

from jym_structural.adapters.sap2000 import (
    ComSap2000Gateway,
    Sap2000AnalysisRunner,
    Sap2000Error,
)
from jym_structural.adapters.sap2000 import __main__ as diagnostic


@pytest.fixture
def analysis_connection():
    analyze = Mock(spec=["RunAnalysis"])
    analyze.RunAnalysis.return_value = 0
    model = Mock(spec=["GetVersion", "GetModelFilename", "GetPresentUnits", "Analyze"])
    model.GetVersion.return_value = ("26.2.0", 26.2, 0)
    model.GetModelFilename.return_value = r"C:\Test\model.sdb"
    model.GetPresentUnits.return_value = 6
    model.Analyze = analyze
    attach = Mock(return_value=Mock(SapModel=model))
    gateway = ComSap2000Gateway(attach=attach)
    gateway.connect_to_running_instance()
    model.reset_mock()
    return gateway, model, attach


def test_analysis_requires_connection_without_attempting_attach():
    attach = Mock()
    gateway = ComSap2000Gateway(attach=attach)
    with pytest.raises(Sap2000Error, match="before running analysis"):
        gateway.run_analysis()
    attach.assert_not_called()


def test_analysis_calls_verified_api_once_and_returns_none(analysis_connection):
    gateway, model, attach = analysis_connection
    runner: Sap2000AnalysisRunner = gateway
    assert runner.run_analysis() is None
    assert model.mock_calls == [call.Analyze.RunAnalysis()]
    attach.assert_called_once_with()


@pytest.mark.parametrize("code", [1, -1, 7])
def test_nonzero_csi_status_fails_without_retry(analysis_connection, code):
    gateway, model, attach = analysis_connection
    model.Analyze.RunAnalysis.return_value = code
    with pytest.raises(Sap2000Error, match=f"CSI return code {code}"):
        gateway.run_analysis()
    model.Analyze.RunAnalysis.assert_called_once_with()
    attach.assert_called_once_with()


@pytest.mark.parametrize("response", [None, False, 0.0, [0], (0,), "0"])
def test_unverified_response_shapes_are_not_interpreted_as_success(analysis_connection, response):
    gateway, model, _ = analysis_connection
    model.Analyze.RunAnalysis.return_value = response
    with pytest.raises(Sap2000Error, match="unexpected CSI response"):
        gateway.run_analysis()
    model.Analyze.RunAnalysis.assert_called_once_with()


def test_com_failure_preserves_cause_and_does_not_reconnect(analysis_connection):
    gateway, model, attach = analysis_connection
    error = OSError("COM disconnected")
    model.Analyze.RunAnalysis.side_effect = error
    with pytest.raises(Sap2000Error, match="COM command failed") as raised:
        gateway.run_analysis()
    assert raised.value.__cause__ is error
    model.Analyze.RunAnalysis.assert_called_once_with()
    attach.assert_called_once_with()


def test_health_does_not_execute_analysis(analysis_connection):
    gateway, model, _ = analysis_connection
    assert gateway.health_check() is True
    model.Analyze.RunAnalysis.assert_not_called()


def test_cli_runs_command_explicitly_without_inventory(analysis_connection, monkeypatch, capsys):
    gateway, model, _ = analysis_connection
    monkeypatch.setattr(diagnostic, "ComSap2000Gateway", lambda: gateway)
    assert diagnostic.main(["--run-analysis"]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out) == {"command": "run_analysis", "status": "completed"}
    assert output.err == ""
    model.Analyze.RunAnalysis.assert_called_once_with()


@pytest.mark.parametrize("failure", [8, OSError("COM failure")])
def test_cli_analysis_failure_has_no_false_success(
    analysis_connection, monkeypatch, capsys, failure
):
    gateway, model, _ = analysis_connection
    if isinstance(failure, Exception):
        model.Analyze.RunAnalysis.side_effect = failure
    else:
        model.Analyze.RunAnalysis.return_value = failure
    monkeypatch.setattr(diagnostic, "ComSap2000Gateway", lambda: gateway)
    assert diagnostic.main(["--run-analysis"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "Analyze.RunAnalysis" in output.err
    model.Analyze.RunAnalysis.assert_called_once_with()


def test_cli_rejects_combined_command_and_query_before_connecting(monkeypatch, capsys):
    factory = Mock()
    monkeypatch.setattr(diagnostic, "ComSap2000Gateway", factory)
    with pytest.raises(SystemExit) as error:
        diagnostic.main(["--run-analysis", "--inventory"])
    assert error.value.code == 2
    factory.assert_not_called()
    assert capsys.readouterr().out == ""
