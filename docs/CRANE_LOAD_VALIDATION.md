# Bridge crane: independent SAP2000 26.2.0 OAPI validation

Standalone scripts, without changes to Core or the SAP2000 adapter:

- `scripts/validate_crane_positions.py`: read-only stage 1.
- `scripts/crane_load_validation.py`: explicit stages 1 through 7.
- `scripts/crane_positions.json`: ordered exact API joint pairs, supplied by the user.

Validated against the already open, user-authorized copy
`C:\Users\Usuario\Downloads\pm_corregido.sdb`. No SAP2000 application was started.
Only the COM helper is created; attachment uses the requested cHelper.GetObject.
Write stages require the exact filename pm_corregido.sdb and the same path recorded
in stage 1, and recheck present units kgf_m_C before writes. No SetPresentUnits,
new model, File.OpenFile, File.Save or File.SaveAs call is used.

## Position table

The API uses numeric strings, without the visual J prefix. No ID normalization
is performed by the scripts.

| Position | Y (m), supplied label | First joint | Second joint |
| --- | --- | --- | --- |
| 01 | 0 | 24 | 25 |
| 02 | 6 | 68 | 69 |
| 03 | 12 | 90 | 91 |
| 04 | 18 | 112 | 113 |
| 05 | 24 | 134 | 135 |
| 06 | 30 | 156 | 157 |
| 07 | 36 | 178 | 179 |
| 08 | 42 | 200 | 201 |
| 09 | 48 | 222 | 223 |
| 10 | 54 | 244 | 245 |
| 11 | 60 | 266 | 267 |

Y labels document the supplied table; they do not determine assignment. Exact
joint IDs from JSON are the assignment inputs. In each pair both joints receive:

- HT_nn: [1050, 0, 0, 0, 0, 0] in kgf/kgf*m, Global.
- HL_nn: [0, 570, 0, 0, 0, 0] in kgf/kgf*m, Global.

## Explicit staged execution

For a new validation on the authorized copy, run one stage at a time using a new
record path. The completed record from this run is **not** a fresh-run input.
Existing HT/HL names cause an explicit collision error; no overwrite or deletion
mode exists. Keep existing PG_HT_POS, PG_HL_POS, PG_HT_Y30, etc. untouched.

```powershell
.venv/Scripts/python.exe scripts/crane_load_validation.py --stage 1 --positions scripts/crane_positions.json --record docs/examples/crane_validation_record.json
```

Advance the stage argument only after the preceding invocation exits successfully:

1. Attach; validate version, file, kgf_m_C, all joints and all 22 planned-name
   collisions. Record the original inventories, SHA256, size and mtime_ns.
2. Create only HT_01/HL_01, load type Other, self-weight 0, AddAnalysisCase=False.
   Assign both points and read back all four force vectors, coordinates and load
   steps. A locked model is unlocked only for these authorized assignments;
   this necessarily invalidates previous results.
3. Recheck stage 2 and remaining collisions, create the other 20 patterns and
   validate all 44 point-force assignments by API readback.
4. Create 22 StaticLinear cases, each with one Load entry referencing the matching
   pattern at scale 1. Verify GetLoads after every SetLoads.
5. Ensure the HT/HL run flags are enabled and call Analyze.RunAnalysis once.
   Existing cases' run flags are not disabled. A persistent analysis-attempt flag
   is written before the call, preventing an automatic second call after failure.
   Require all 22 cases to report finished status 4.
6. Save current case/combo output selection, deselect all and select each HT/HL
   individually. Read FrameForce for group ALL (GroupElm) and verify that all
   enumerated frames occur and each returned LoadCase is the selected case.
   Export complete rows, including Obj, ObjSta, Elm, ElmSta, LoadCase, StepType,
   StepNum and all six components. Restore and verify original output selection.
7. Build signed minimum/maximum and absolute extreme per component over these
   22 cases and all frames. Preserve full controlling rows in JSON and provenance
   columns in CSV. Absolute extreme retains its sign and also stores magnitude.

The local record gates every stage and rejects changed position tables, stage
skips and repeated stages. CSI is not transactional: if a write fails midway,
the script stops explicitly and does not automatically delete or rewrite data.
Inspect partial state before proceeding. The sole recovery option
`--stage 2 --verify-existing-stage2` verifies the first pair without writing,
requires precisely the original inventories plus that pair's patterns, and marks
stage 2 complete only when all load readbacks pass.

## Installed signatures and COM peculiarities

Signatures were inspected from the locally generated comtypes SAP2000v1 typelib,
not inferred from ETABS documentation:

| Operation | Actual relevant behavior |
| --- | --- |
| GetVersion | version, version number, CSI code |
| GetPresentUnits | direct enum; kgf_m_C = 8, no separate CSI code |
| GetModelFilename(True) | direct path, no separate CSI code |
| GetModelIsLocked | direct bool, no separate CSI code |
| LoadPatterns.Add | Name, MyType, SelfWTMultiplier=0, AddAnalysisCase=False; scalar CSI code |
| PointObj.SetLoadForce | Name, LoadPat, Value, Replace=False, CSys="Global", ItemType=Objects; returns Value and CSI code |
| PointObj.GetLoadForce | Name, NumberItems and ten in/out arrays, ItemType; returns count, arrays and CSI code |
| StaticLinear.SetCase | Name; scalar CSI code |
| StaticLinear.SetLoads | Name, NumberLoads, LoadType, LoadName, SF; returns three arrays and CSI code |
| StaticLinear.GetLoads | Name, NumberLoads, LoadType, LoadName, SF; returns count, arrays and CSI code |
| Results.FrameForce | Name, ItemTypeElm, NumberResults and 13 arrays; returns count, arrays and CSI code |

Every available CSI code is checked, including reads, selections, restoration,
run flags and analysis. Nonzero or malformed responses raise errors. In/out
arrays are handled inside the standalone script. SAP2000 readback spells global
coordinates as GLOBAL; validation accepts that and Global, without normalizing IDs.

During stage 2 the initial readback check stopped on this capitalization difference
after creating the correct four assignments. The installed response was inspected,
the check corrected, and the stage completed through read-only recovery. No second
SetLoadForce was made for that pair.

## Real validation results

- SAP2000 26.2.0, 254 joints, 449 frames; units remained kgf_m_C throughout.
- 22 new patterns, 22 new cases, 44 point assignments; original 15 pattern names
  and 15 case names remain present. No write call targeted any original PG case.
- One Analyze.RunAnalysis call; all 22 HT/HL cases finished with status 4.
- 3,783 rows per case, 83,226 total, with P/V2/V3 in kgf and T/M2/M3 in kgf*m.
- Output selection restored; final model lock is True after analysis.
- Stage 1 SHA256 and timestamp unchanged during read-only validation:
  `1a9769e998597585b5eaddb1c2e69dd9c5c4fdc0872401a6692fc85393191840`.
- Final SHA256 after the requested loads/analysis:
  `aa93d6b7b73e74615d70f67262580348b1edb008cc120a18b714d8b0c1861721`.
  The .sdb grew from 116588 to 131638 bytes. Analysis persisted changes; no
  claim of unchanged file is made for this write task. Exact mtime_ns values
  before/after are in the validation record.

| Component | Min | Case / frame / ObjSta | Max | Case / frame / ObjSta | Absolute magnitude |
| --- | ---: | --- | ---: | --- | ---: |
| P | -1246.468 | HT_11 / 393 / 0 | 1138.055 | HT_01 / 276 / 0 | 1246.468 |
| V2 | -272.975 | HT_11 / 237 / 0 | 731.925 | HT_01 / 4 / 0 | 731.925 |
| V3 | -718.301 | HT_09 / 192 / 0 | 726.952 | HT_02 / 87 / 0 | 726.952 |
| T | -10.981 | HT_01 / 3 / 0 | 11.855 | HT_11 / 238 / 0 | 11.855 |
| M2 | -943.223 | HT_02 / 274 / 0 | 918.262 | HT_02 / 6 / 0 | 943.223 |
| M3 | -1468.953 | HT_01 / 4 / 5.86 | 2820.127 | HT_01 / 4 / 0 | 2820.127 |

Station values are in m. Signed absolute-controlling values and their full
case/frame/object station/element station/step provenance are in JSON and CSV.
Tie policy is deterministic: value then provenance; equal absolute magnitudes
prefer the negative value, then provenance. Only explicit HT/HL output is enveloped,
not existing PG cases or load combinations.

## Files and verification

- `docs/examples/crane_validation_record.json`: stage gates, inventories and final
  real readback checks, file fingerprints and summary counts.
- `docs/examples/crane_frame_results.jsonl`: 83,226 raw traceable rows (~23 MB),
  preserved for audit rather than duplicated in this document.
- `docs/examples/crane_envelope.json`: complete controlling source rows.
- `docs/examples/crane_envelope.csv`: six-row table with each extreme's provenance.

Independent recomputation from all exported rows confirmed all six signed minima,
maxima and absolute magnitudes. Added 17 standalone unit tests for input tables,
CSI codes, guards, outputs and signed/provenance-preserving envelopes.

Validation: 758 tests passed using
`pytest -q --basetemp .venv/pytest-crane-validation`; the default Windows pytest
temporary directory is inaccessible in this environment. One pre-existing pytest
cache permission warning remains. `ruff check src tests scripts` and
`git diff --check` pass. No Core/adapter changes, push, merge or commit were made.
