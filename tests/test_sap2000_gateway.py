import json
from unittest.mock import Mock, call

import pytest

from jym_structural.adapters.sap2000 import (
    ComSap2000Gateway,
    Sap2000ConnectionGateway,
    Sap2000Error,
    Sap2000ModelReader,
    gateway,
)
from jym_structural.adapters.sap2000 import __main__ as diagnostic
from jym_structural.core.models import ModelInfo


@pytest.fixture
def application():
    model = Mock(spec=["GetVersion", "GetModelFilename", "GetPresentUnits"])
    model.GetVersion.return_value = ["26.0.0", 26.0, 0]
    model.GetModelFilename.return_value = r"C:\Models\pórtico.sdb"
    model.GetPresentUnits.return_value = 6
    return Mock(SapModel=model)


def test_connection_normalizes_metadata_and_only_reads(application):
    attach = Mock(return_value=application)
    adapter: Sap2000ConnectionGateway = ComSap2000Gateway(attach=attach)
    assert adapter.health_check() is False
    attach.assert_not_called()
    info = adapter.connect_to_running_instance()
    assert isinstance(info, ModelInfo)
    assert info.model_dump() == {
        "software": "SAP2000",
        "version": "26.0.0",
        "model_name": "pórtico.sdb",
        "model_path": r"C:\Models\pórtico.sdb",
        "units": "kN_m_C",
    }
    assert application.SapModel.mock_calls == [
        call.GetVersion(),
        call.GetModelFilename(True),
        call.GetPresentUnits(),
    ]
    assert adapter.health_check() is True
    attach.assert_called_once_with()


def test_connection_does_not_expose_later_capabilities():
    assert Sap2000ConnectionGateway in ComSap2000Gateway.__bases__
    assert Sap2000ModelReader in ComSap2000Gateway.__bases__
    adapter = ComSap2000Gateway()
    for method in ("run_analysis", "get_member_results"):
        assert not hasattr(adapter, method)


@pytest.mark.parametrize(
    "code,name",
    enumerate(
        (
            "lb_in_F",
            "lb_ft_F",
            "kip_in_F",
            "kip_ft_F",
            "kN_mm_C",
            "kN_m_C",
            "kgf_mm_C",
            "kgf_m_C",
            "N_mm_C",
            "N_m_C",
            "Ton_mm_C",
            "Ton_m_C",
            "kN_cm_C",
            "kgf_cm_C",
            "N_cm_C",
            "Ton_cm_C",
        ),
        start=1,
    ),
)
def test_present_units(application, code, name):
    application.SapModel.GetPresentUnits.return_value = code
    assert ComSap2000Gateway(attach=lambda: application).connect_to_running_instance().units == name


@pytest.mark.parametrize(
    "method,value,message",
    [
        ("GetVersion", ["26", 26, 7], "CSI return code 7"),
        ("GetVersion", ["", 26, 0], "invalid version"),
        ("GetVersion", ["26", 26], "Could not attach"),
        ("GetModelFilename", "", "No saved model"),
        ("GetPresentUnits", 0, "unsupported units"),
        ("GetPresentUnits", 17, "unsupported units"),
    ],
)
def test_invalid_responses_fail_and_do_not_connect(application, method, value, message):
    getattr(application.SapModel, method).return_value = value
    adapter = ComSap2000Gateway(attach=lambda: application)
    with pytest.raises(Sap2000Error, match=message):
        adapter.connect_to_running_instance()
    assert adapter.health_check() is False


def test_com_failure_is_wrapped_and_health_does_not_reconnect(application):
    attach = Mock(return_value=application)
    adapter = ComSap2000Gateway(attach=attach)
    adapter.connect_to_running_instance()
    application.SapModel.GetVersion.side_effect = OSError("disconnected")
    assert adapter.health_check() is False
    attach.assert_called_once_with()
    attach.side_effect = OSError("no running instance")
    with pytest.raises(Sap2000Error) as error:
        adapter.connect_to_running_instance()
    assert isinstance(error.value.__cause__, OSError)
    assert adapter.health_check() is False


def test_non_windows_attachment_fails_cleanly(monkeypatch):
    monkeypatch.setattr(gateway.sys, "platform", "linux")
    with pytest.raises(Sap2000Error, match="requires Windows"):
        ComSap2000Gateway().connect_to_running_instance()


def test_no_accessible_instance():
    adapter = ComSap2000Gateway(attach=lambda: None)
    with pytest.raises(Sap2000Error, match="No accessible running"):
        adapter.connect_to_running_instance()
    assert adapter.health_check() is False


def test_health_checks_csi_status_and_current_model(application):
    adapter = ComSap2000Gateway(attach=lambda: application)
    adapter.connect_to_running_instance()
    application.SapModel.GetVersion.return_value = ["26", 26, 1]
    assert adapter.health_check() is False
    application.SapModel.GetVersion.return_value = ["26", 26, 0]
    application.SapModel.GetModelFilename.return_value = ""
    assert adapter.health_check() is False


def test_diagnostic_json(application, monkeypatch, capsys):
    monkeypatch.setattr(
        diagnostic,
        "ComSap2000Gateway",
        lambda: ComSap2000Gateway(
            attach=lambda: application,
        ),
    )
    assert diagnostic.main([]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out)["model_name"] == "pórtico.sdb"
    assert output.err == ""


def test_diagnostic_failure(monkeypatch, capsys):
    adapter = Mock()
    adapter.connect_to_running_instance.side_effect = Sap2000Error("no instance")
    monkeypatch.setattr(diagnostic, "ComSap2000Gateway", lambda: adapter)
    assert diagnostic.main([]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "no instance" in output.err
