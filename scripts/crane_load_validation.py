"""Staged SAP2000 26.2.0 crane load validation on pm_corregido.sdb only.

Execute each stage separately; every stage requires the previous recorded success.
Never rerun a failed write stage blindly: CSI operations are not transactional.
"""

import argparse
import csv
import json
import math
from pathlib import Path

from validate_crane_positions import file_state, names_from_reply, read_positions, validate_stage1

COMPONENTS = ("P", "V2", "V3", "T", "M2", "M3")
RESULT_ARRAYS = ("Obj", "ObjSta", "Elm", "ElmSta", "LoadCase", "StepType", "StepNum", *COMPONENTS)


def case_status(model, names):
    count, cases, statuses = checked(
        "Analyze.GetCaseStatus", model.Analyze.GetCaseStatus(0, [], []), 3
    )
    if count != len(cases) or count != len(statuses):
        raise RuntimeError("GetCaseStatus inconsistent arrays")
    result = dict(zip(cases, statuses, strict=True))
    if any(result.get(name) != 4 for name in names):
        raise RuntimeError(f"Cases not finished (CSI status 4): {result}")
    return {name: result[name] for name in names}


def output_selection(model):
    _, cases = inventory(model)
    combos = names_from_reply("RespCombo.GetNameList", model.RespCombo.GetNameList(0, []))
    saved = {"cases": [], "combos": []}
    for names, getter, key in (
        (cases, model.Results.Setup.GetCaseSelectedForOutput, "cases"),
        (combos, model.Results.Setup.GetComboSelectedForOutput, "combos"),
    ):
        for name in names:
            (selected,) = checked(f"GetSelected({name})", getter(name, False), 1)
            if selected:
                saved[key].append(name)
    return saved


def read_results(model, items, api, path, target):
    frames = names_from_reply("FrameObj.GetNameList", model.FrameObj.GetNameList(0, []))
    saved = output_selection(model)
    row_count = 0
    per_case = {}
    try:
        with target.open("x", encoding="utf-8") as stream:
            for name, _, _ in items:
                guard(model, path, api)
                checked(
                    "DeselectAllCasesAndCombosForOutput",
                    model.Results.Setup.DeselectAllCasesAndCombosForOutput(),
                )
                checked(
                    f"SetCaseSelectedForOutput({name})",
                    model.Results.Setup.SetCaseSelectedForOutput(name, True),
                )
                (selected,) = checked(
                    f"GetCaseSelectedForOutput({name})",
                    model.Results.Setup.GetCaseSelectedForOutput(name, False),
                    1,
                )
                if not selected:
                    raise RuntimeError(f"{name}: output selection not applied")
                args = {field: [] for field in RESULT_ARRAYS}
                count, *arrays = checked(
                    f"FrameForce({name}, ALL)",
                    model.Results.FrameForce(
                        Name="ALL", ItemTypeElm=api.eItemTypeElm_GroupElm, NumberResults=0, **args
                    ),
                    14,
                )
                if (
                    type(count) is not int
                    or count <= 0
                    or any(len(array) != count for array in arrays)
                ):
                    raise RuntimeError(f"{name}: inconsistent or empty FrameForce arrays")
                if set(arrays[0]) != set(frames):
                    raise RuntimeError(f"{name}: ALL group did not return every frame")
                for values in zip(*arrays, strict=True):
                    row = dict(zip(RESULT_ARRAYS, values, strict=True))
                    if row["LoadCase"] != name:
                        raise RuntimeError(f"Unexpected case in output: {row['LoadCase']}")
                    for field in ("ObjSta", "ElmSta", "StepNum", *COMPONENTS):
                        if not math.isfinite(row[field]):
                            raise RuntimeError(f"Nonfinite result {name}/{field}")
                    stream.write(json.dumps(row) + "\n")
                per_case[name] = count
                row_count += count
    finally:
        guard(model, path, api)
        checked(
            "Restore output deselection", model.Results.Setup.DeselectAllCasesAndCombosForOutput()
        )
        for name in saved["cases"]:
            checked(
                f"Restore case {name}", model.Results.Setup.SetCaseSelectedForOutput(name, True)
            )
        for name in saved["combos"]:
            checked(
                f"Restore combo {name}", model.Results.Setup.SetComboSelectedForOutput(name, True)
            )
    if output_selection(model) != saved:
        raise RuntimeError("Output selection restoration verification failed")
    return {
        "frame_count": len(frames),
        "row_count": row_count,
        "rows_per_case": per_case,
        "results_file": str(target),
        "output_selection_restored": saved,
    }


def build_envelope(source, target):
    extrema = {}
    with source.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            provenance = (
                row["LoadCase"],
                row["Obj"],
                row["ObjSta"],
                row["Elm"],
                row["ElmSta"],
                row["StepType"],
                row["StepNum"],
            )
            for component in COMPONENTS:
                value = row[component]
                keys = {
                    "minimum": (value, provenance),
                    "maximum": (-value, provenance),
                    "absolute": (-abs(value), value, provenance),
                }
                slots = extrema.setdefault(component, {})
                for kind, key in keys.items():
                    if kind not in slots or key < slots[kind][0]:
                        slots[kind] = (key, {"value": value, "magnitude": abs(value), **row})
    if set(extrema) != set(COMPONENTS):
        raise RuntimeError("No complete envelope data")
    result = {c: {kind: pair[1] for kind, pair in extrema[c].items()} for c in COMPONENTS}
    target.write_text(json.dumps(result, indent=2), encoding="utf-8")
    csv_path = target.with_suffix(".csv")
    with csv_path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "Component",
                "Unit",
                *[
                    f"{kind} {label}"
                    for kind in ("Min", "Max", "Abs")
                    for label in (
                        "Value",
                        "Case",
                        "Frame",
                        "ObjSta",
                        "Element",
                        "ElmSta",
                        "StepType",
                        "StepNum",
                    )
                ],
            ]
        )
        for component in COMPONENTS:
            values = [component, "kgf" if component in ("P", "V2", "V3") else "kgf*m"]
            for kind in ("minimum", "maximum", "absolute"):
                row = result[component][kind]
                values.extend(
                    [
                        row["value"],
                        row["LoadCase"],
                        row["Obj"],
                        row["ObjSta"],
                        row["Elm"],
                        row["ElmSta"],
                        row["StepType"],
                        row["StepNum"],
                    ]
                )
            writer.writerow(values)
    return {"json_file": str(target), "csv_file": str(csv_path), "envelope": result}


def checked(operation, reply, outputs=0):
    if outputs:
        if not isinstance(reply, (list, tuple)) or len(reply) != outputs + 1:
            raise RuntimeError(f"{operation}: unexpected response {reply!r}")
        values, code = reply[:-1], reply[-1]
    else:
        values, code = (), reply
    if type(code) is not int or code != 0:
        raise RuntimeError(f"{operation}: CSI return code {code!r}")
    return values


def planned(positions):
    return [
        (f"{direction}_{index:02d}", pair, vector)
        for index, pair in enumerate(positions, 1)
        for direction, vector in (
            ("HT", [1050.0, 0.0, 0.0, 0.0, 0.0, 0.0]),
            ("HL", [0.0, 570.0, 0.0, 0.0, 0.0, 0.0]),
        )
    ]


def guard(model, path, api):
    current = model.GetModelFilename(True)
    if Path(current) != Path(path) or Path(current).name != "pm_corregido.sdb":
        raise RuntimeError(f"Unauthorized model: {current!r}")
    if model.GetPresentUnits() != api.eUnits_kgf_m_C:
        raise RuntimeError("Expected exactly kgf_m_C; no units were changed")


def inventory(model):
    patterns = names_from_reply("LoadPatterns.GetNameList", model.LoadPatterns.GetNameList(0, []))
    cases = names_from_reply("LoadCases.GetNameList", model.LoadCases.GetNameList(0, [], 0))
    return patterns, cases


def verify_loads(model, items, api):
    expected_patterns = {name for name, _, _ in items}
    for name, pair, vector in items:
        (load_type,) = checked(f"GetLoadType({name})", model.LoadPatterns.GetLoadType(name, 0), 1)
        (self_weight,) = checked(
            f"GetSelfWTMultiplier({name})", model.LoadPatterns.GetSelfWTMultiplier(name, 0.0), 1
        )
        if load_type != api.eLoadPatternType_Other or self_weight != 0:
            raise RuntimeError(f"{name}: unexpected pattern type/self weight")
        for point in pair:
            result = checked(
                f"GetLoadForce({point})",
                model.PointObj.GetLoadForce(point, 0, [], [], [], [], [], [], [], [], [], [], 0),
                11,
            )
            count, point_names, pats, steps, systems, *components = result
            arrays = [point_names, pats, steps, systems, *components]
            if any(len(array) != count for array in arrays):
                raise RuntimeError(f"{point}: inconsistent load arrays")
            matches = [i for i, pattern in enumerate(pats) if pattern == name]
            if len(matches) != 1:
                raise RuntimeError(
                    f"{point}/{name}: expected one force assignment, got {len(matches)}"
                )
            i = matches[0]
            actual = [array[i] for array in components]
            if (
                point_names[i] != point
                or systems[i] not in ("Global", "GLOBAL")
                or steps[i] != 0
                or actual != vector
            ):
                raise RuntimeError(f"{point}/{name}: readback mismatch {actual!r}")
    return {
        "patterns_verified": sorted(expected_patterns),
        "joint_assignments_verified": 2 * len(items),
    }


def add_patterns(model, items, api, path):
    for name, pair, vector in items:
        guard(model, path, api)
        checked(
            f"LoadPatterns.Add({name})",
            model.LoadPatterns.Add(name, api.eLoadPatternType_Other, 0.0, False),
        )
        for point in pair:
            guard(model, path, api)
            (returned,) = checked(
                f"SetLoadForce({point}/{name})",
                model.PointObj.SetLoadForce(
                    point, name, vector.copy(), False, "Global", api.eItemType_Objects
                ),
                1,
            )
            if list(returned) != vector:
                raise RuntimeError(f"SetLoadForce({point}/{name}): altered vector")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=int, choices=range(1, 8), required=True)
    parser.add_argument("--positions", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument(
        "--verify-existing-stage2",
        action="store_true",
        help="Read-only recovery of the first pair after interrupted readback",
    )
    args = parser.parse_args()
    positions = read_positions(args.positions)
    items = planned(positions)

    import comtypes.client

    helper = comtypes.client.CreateObject("SAP2000v1.Helper")
    from comtypes.gen import SAP2000v1 as api

    helper = helper.QueryInterface(api.cHelper)
    sap_object = helper.GetObject("CSI.SAP2000.API.SapObject")
    if sap_object is None:
        raise RuntimeError("No existing SAP2000 instance accessible")
    model = sap_object.SapModel
    path = model.GetModelFilename(True)
    guard(model, path, api)
    if args.stage == 1:
        if args.record.exists():
            raise RuntimeError("Record already exists; refusing to overwrite")
        record = {
            "stage1": validate_stage1(model, positions, api.eUnits_kgf_m_C),
            "positions": positions,
        }
        patterns, cases = inventory(model)
        conflicts = sorted({name for name, _, _ in items} & (set(patterns) | set(cases)))
        if conflicts:
            raise RuntimeError(f"Existing patterns/cases conflict: {conflicts}")
        record["original_patterns"], record["original_cases"] = patterns, cases
        record["model_path"] = path
        record["completed_stage"] = 1
    else:
        record = json.loads(args.record.read_text(encoding="utf-8"))
        if record["completed_stage"] != args.stage - 1:
            raise RuntimeError(
                "Previous stage has not been validated; stages cannot be skipped or rerun"
            )
        if record["positions"] != [list(pair) for pair in positions]:
            raise RuntimeError("Position table changed since stage 1")
        guard(model, record["model_path"], api)
        if args.stage == 2:
            patterns, cases = inventory(model)
            if args.verify_existing_stage2:
                expected = set(record["original_patterns"]) | {name for name, _, _ in items[:2]}
                if set(patterns) != expected or set(cases) != set(record["original_cases"]):
                    raise RuntimeError(
                        "Recovery inventory differs from original plus stage 2 patterns"
                    )
                record["stage2"] = verify_loads(model, items[:2], api)
                record["stage2"]["recovered_by_readback_only"] = True
                record["completed_stage"] = 2
                args.record.write_text(json.dumps(record, indent=2), encoding="utf-8")
                print(json.dumps(record["stage2"], indent=2))
                return
            conflicts = sorted({name for name, _, _ in items} & (set(patterns) | set(cases)))
            if conflicts:
                raise RuntimeError(f"Existing patterns/cases conflict: {conflicts}")
            if model.GetModelIsLocked():
                guard(model, path, api)
                checked("SetModelIsLocked(False)", model.SetModelIsLocked(False))
                if model.GetModelIsLocked():
                    raise RuntimeError("Model remained locked after unlock")
                record["unlocked_for_authorized_load_assignment"] = True
            add_patterns(model, items[:2], api, path)
            record["stage2"] = verify_loads(model, items[:2], api)
        elif args.stage == 3:
            verify_loads(model, items[:2], api)
            patterns, cases = inventory(model)
            conflicts = sorted({name for name, _, _ in items[2:]} & (set(patterns) | set(cases)))
            if conflicts:
                raise RuntimeError(f"Existing patterns/cases conflict: {conflicts}")
            add_patterns(model, items[2:], api, path)
            record["stage3"] = verify_loads(model, items, api)
        elif args.stage == 4:
            verify_loads(model, items, api)
            _, cases = inventory(model)
            conflicts = sorted({name for name, _, _ in items} & set(cases))
            if conflicts:
                raise RuntimeError(f"Existing cases conflict: {conflicts}")
            for name, _, _ in items:
                guard(model, path, api)
                checked(f"StaticLinear.SetCase({name})", model.LoadCases.StaticLinear.SetCase(name))
                types, names, scales = checked(
                    f"StaticLinear.SetLoads({name})",
                    model.LoadCases.StaticLinear.SetLoads(name, 1, ["Load"], [name], [1.0]),
                    3,
                )
                if list(types) != ["Load"] or list(names) != [name] or list(scales) != [1.0]:
                    raise RuntimeError(f"{name}: SetLoads modified its arrays")
                count, types, names, scales = checked(
                    f"StaticLinear.GetLoads({name})",
                    model.LoadCases.StaticLinear.GetLoads(name, 0, [], [], []),
                    4,
                )
                if (
                    count != 1
                    or list(types) != ["Load"]
                    or list(names) != [name]
                    or list(scales) != [1.0]
                ):
                    raise RuntimeError(f"{name}: case readback mismatch")
            record["stage4"] = {"cases_verified": [name for name, _, _ in items]}
        elif args.stage == 5:
            verify_loads(model, items, api)
            if record.get("analysis_attempted"):
                raise RuntimeError("Analysis was already attempted; refusing to run it twice")
            for name, _, _ in items:
                guard(model, path, api)
                checked(
                    f"Analyze.SetRunCaseFlag({name})",
                    model.Analyze.SetRunCaseFlag(name, True, False),
                )
            record["analysis_attempted"] = True
            record["file_before_analysis"] = file_state(Path(path))
            args.record.write_text(json.dumps(record, indent=2), encoding="utf-8")
            guard(model, path, api)
            checked("Analyze.RunAnalysis", model.Analyze.RunAnalysis())
            record["stage5"] = {
                "run_analysis_calls": 1,
                "case_status": case_status(model, [n for n, _, _ in items]),
            }
        elif args.stage == 6:
            case_status(model, [n for n, _, _ in items])
            target = args.record.with_name("crane_frame_results.jsonl")
            record["stage6"] = read_results(model, items, api, path, target)
        elif args.stage == 7:
            record["stage7"] = build_envelope(
                Path(record["stage6"]["results_file"]), args.record.with_name("crane_envelope.json")
            )
        record["completed_stage"] = args.stage
    record["file_state_after_stage"] = file_state(Path(path))
    args.record.parent.mkdir(parents=True, exist_ok=True)
    args.record.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {"completed_stage": args.stage, "model_path": path, "record": str(args.record)},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
