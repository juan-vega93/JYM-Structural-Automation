"""Stage 1 only: attach, check present units and validate exact point IDs.

Run with the repository's Windows Python/comtypes environment:
    python scripts/validate_crane_positions.py --positions positions.json

positions.json contains an ordered JSON array of two-ID arrays. IDs are exact
SAP2000 API names; no J-prefix removal or other normalization is performed.
There are intentionally no model writes, case configuration or analysis calls.
"""

import argparse
import hashlib
import json
from pathlib import Path


def read_positions(path: Path) -> list[tuple[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list) or not data:
        raise ValueError("positions must be a nonempty ordered JSON array")
    positions = []
    for index, pair in enumerate(data, 1):
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError(f"Position {index}: expected exactly two joint IDs")
        if any(not isinstance(name, str) or not name.strip() for name in pair):
            raise ValueError(f"Position {index}: joint IDs must be nonblank strings")
        if pair[0] == pair[1]:
            raise ValueError(f"Position {index}: the two joints must be distinct")
        positions.append(tuple(pair))
    return positions


def file_state(path: Path) -> dict:
    stat = path.stat()
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"sha256": digest, "mtime_ns": stat.st_mtime_ns, "size": stat.st_size}


def names_from_reply(operation: str, reply: object) -> list[str]:
    if not isinstance(reply, (list, tuple)) or len(reply) != 3:
        raise RuntimeError(f"{operation}: unexpected comtypes response {reply!r}")
    count, names, code = reply
    if type(code) is not int or code != 0:
        raise RuntimeError(f"{operation}: CSI return code {code!r}")
    if type(count) is not int or count < 0:
        raise RuntimeError(f"{operation}: invalid count {count!r}")
    if names is None and count == 0:
        names = []
    if not isinstance(names, (list, tuple)) or len(names) != count:
        raise RuntimeError(f"{operation}: inconsistent name array")
    if any(not isinstance(name, str) or not name for name in names):
        raise RuntimeError(f"{operation}: invalid name")
    if len(set(names)) != len(names):
        raise RuntimeError(f"{operation}: duplicate names")
    return list(names)


def validate_stage1(model, positions, expected_units: int) -> dict:
    version, _number, code = model.GetVersion()
    if type(code) is not int or code != 0:
        raise RuntimeError(f"GetVersion: CSI return code {code!r}")
    if version != "26.2.0":
        raise RuntimeError(f"Expected SAP2000 26.2.0; connected version is {version!r}")
    model_filename = model.GetModelFilename(True)
    if not isinstance(model_filename, str) or not model_filename.strip():
        raise RuntimeError("No saved model path is available")
    path = Path(model_filename)
    if path.suffix.lower() != ".sdb" or not path.is_file():
        raise RuntimeError(f"Expected an existing .sdb file: {path}")
    before = file_state(path)
    units = model.GetPresentUnits()  # Direct enum return, not a CSI status code.
    if units != expected_units:
        raise RuntimeError(f"Expected exactly kgf_m_C ({expected_units}); got {units!r}")
    names = names_from_reply("PointObj.GetNameList", model.PointObj.GetNameList(0, []))
    existing = set(names)
    missing = sorted({name for pair in positions for name in pair} - existing)
    if missing:
        raise RuntimeError(f"Joint IDs not found (exact match required): {missing}")
    after = file_state(path)
    if before != after:
        raise RuntimeError("The .sdb file changed during stage 1")
    return {
        "stage": 1,
        "validated": True,
        "version": version,
        "model_path": str(path),
        "model_name": path.name,
        "units": "kgf_m_C",
        "joint_count": len(names),
        "position_count": len(positions),
        "positions": [
            {
                "position": index,
                "joints": pair,
                "planned_patterns": [f"HT_{index:02d}", f"HL_{index:02d}"],
            }
            for index, pair in enumerate(positions, 1)
        ],
        "file_before": before,
        "file_after": after,
        "writes_performed": False,
        "analysis_performed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--positions", type=Path, required=True)
    args = parser.parse_args()
    positions = read_positions(args.positions)

    import comtypes.client

    helper = comtypes.client.CreateObject("SAP2000v1.Helper")
    from comtypes.gen import SAP2000v1

    helper = helper.QueryInterface(SAP2000v1.cHelper)
    sap_object = helper.GetObject("CSI.SAP2000.API.SapObject")
    if sap_object is None:
        raise RuntimeError("No existing SAP2000 instance accessible; no new instance was started")
    SapModel = sap_object.SapModel
    print(json.dumps(validate_stage1(SapModel, positions, SAP2000v1.eUnits_kgf_m_C), indent=2))


if __name__ == "__main__":
    main()
