"""Standalone validation script checks; no COM or running SAP2000 required."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.fixture
def scripts(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    loaded = []
    for name in ("validate_crane_positions", "crane_load_validation"):
        spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
        loaded.append(module)
    return loaded


def test_position_table_and_vectors(scripts):
    stage1, stages = scripts
    positions = stage1.read_positions(SCRIPTS / "crane_positions.json")
    assert len(positions) == 11
    items = stages.planned(positions)
    assert items[0] == ("HT_01", ("24", "25"), [1050.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    assert items[-1] == ("HL_11", ("266", "267"), [0.0, 570.0, 0.0, 0.0, 0.0, 0.0])


@pytest.mark.parametrize("data", [[], {}, [["24"]], [[24, 25]], [["24", "24"]], [["", "25"]]])
def test_invalid_position_tables(scripts, tmp_path, data):
    path = tmp_path / "positions.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        scripts[0].read_positions(path)


@pytest.mark.parametrize("reply,outputs", [(1, 0), (([], 4), 1), (False, 0), (([],), 1)])
def test_csi_errors_explicit(scripts, reply, outputs):
    with pytest.raises(RuntimeError):
        scripts[1].checked("operation", reply, outputs)


def test_comtypes_array_return_keeps_outputs(scripts):
    assert scripts[1].checked("SetLoadForce", ([1, 2], 0), 1) == ([1, 2],)


@pytest.mark.parametrize("reply", [(2, ["24"], 0), (1, ["24"], 9), (2, ["24", "24"], 0)])
def test_bad_joint_arrays(scripts, reply):
    with pytest.raises(RuntimeError):
        scripts[0].names_from_reply("GetNameList", reply)


def test_model_guard_checks_name_path_units(scripts):
    class Model:
        path = "C:/models/pm_corregido.sdb"
        units = 8

        def GetModelFilename(self, include_path):
            return self.path

        def GetPresentUnits(self):
            return self.units

    class API:
        eUnits_kgf_m_C = 8

    model = Model()
    scripts[1].guard(model, model.path, API)
    with pytest.raises(RuntimeError, match="Unauthorized"):
        scripts[1].guard(model, "C:/other/pm_corregido.sdb", API)
    model.units = 6
    with pytest.raises(RuntimeError, match="kgf_m_C"):
        scripts[1].guard(model, model.path, API)
    model.path = "C:/models/original.sdb"
    with pytest.raises(RuntimeError, match="Unauthorized"):
        scripts[1].guard(model, model.path, API)


def test_signed_envelope_retains_actual_rows_and_stations(scripts, tmp_path):
    source = tmp_path / "rows.jsonl"
    rows = []
    for case, station, value in (("HT_02", 2, 10), ("HT_01", 1, -10), ("HL_01", 3, 4)):
        rows.append(
            {
                "Obj": "frame",
                "ObjSta": station,
                "Elm": "element",
                "ElmSta": station,
                "LoadCase": case,
                "StepType": "",
                "StepNum": 0,
                **dict.fromkeys(scripts[1].COMPONENTS, value),
            }
        )
    source.write_text("\n".join(json.dumps(row) for row in rows))
    result = scripts[1].build_envelope(source, tmp_path / "envelope.json")["envelope"]
    for component in scripts[1].COMPONENTS:
        assert result[component]["minimum"]["value"] == -10
        assert result[component]["maximum"]["value"] == 10
        assert result[component]["absolute"]["value"] == -10
        assert result[component]["absolute"]["magnitude"] == 10
        assert result[component]["absolute"]["LoadCase"] == "HT_01"
        assert result[component]["absolute"]["ObjSta"] == 1
