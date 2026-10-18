# Steel flexural yield capacity (A0.6)

This is the first calculated capacity in the project. It consumes the supplied
A0.4 material/section properties and returns the existing A0.5 `CapacityValue`.
The calculation lives in `src/jym_structural/design/steel/flexure.py`, outside
the neutral Core data models. Dependencies point from design to Core.

## Public API and calculation

```python
from jym_structural.design.steel import steel_flexural_yield_capacity

# Signature:
# steel_flexural_yield_capacity(
#     material: MaterialProperties, section: SectionProperties, *,
#     component: Literal["m2", "m3"], section_axis: Literal["x", "y"],
#     factor: float, member_id: str | None = None,
#     source: PropertySource | None = None,
# ) -> CapacityValue
```

The only capacity formula is **capacity = factor × material.fy × Z**.
`section_axis="x"` selects `section.zx`; `section_axis="y"` selects `section.zy`.
It never uses Sx/Sy. Component and section_axis are independent required inputs:
both m2 and m3 can be explicitly paired with either x or y. The function neither
infers orientation nor chooses a strong/weak axis by comparing properties.

`factor` is required and must be a finite positive number; integers are accepted,
booleans and strings are rejected without coercion. There is no default or implied
LRFD/ASD meaning. Its interpretation and origin belong to the caller. Existing
property instances are revalidated, including instances produced using unchecked
`model_copy(update=...)`. The function does not infer a steel grade from a name,
restrict a section family, resolve material references or modify the inputs.

Invalid component/axis/unit combinations raise explicit ValueError. Invalid factor,
properties or output fields raise Pydantic ValidationError (a ValueError subclass).
Non-property objects raise TypeError. Nonfinite or zero results from floating-point
overflow/underflow are rejected by CapacityValue's positive finite validation.

## Exact supported units

| MaterialUnits.stress | SectionUnits.length | Plastic modulus | Output unit |
| --- | --- | --- | --- |
| MPa | mm | mm^3 | N*mm |

The fixed dimensional identity is MPa = N/mm², hence Fy × Z has units N·mm.
No numeric scale change is applied. All other pairs fail as **unsupported**, not
physically invalid: examples include ksi/in, kgf/cm^2/cm and MPa/m. Labels must
match exactly, including case and whitespace. No parser, normalization, output-unit
override or general conversion engine is provided. A result is never relabelled
as kN*m. DemandCheck therefore requires a demand in exactly N*mm too.

## Output and traceability

The returned frozen CapacityValue records the caller's component and optional
member_id, `section_name=section.name`, `material_name=material.name`, unit N*mm
and stable `limit_state="steel_flexural_yielding"`. Caller-supplied PropertySource
is preserved. When source is absent the output source remains None; property
provenance is not substituted for calculation provenance and no standard is
invented. Names and references are preserved exactly.

The output supports the existing JSON round trip and deep copy contracts.
The function is pure and repeatable. CapacityValue is intentionally unchanged:
it does not contain a calculation-input history. Retain the input properties,
explicit axis mapping and factor with the calling workflow when a complete
recomputation record is needed.

## Synthetic example and DemandCheck integration

These are supplied synthetic values, not a real profile or verified catalog entry.

```python
from jym_structural.core import (
    CapacityValue, ForceExtreme, FrameForces, MaterialProperties, MaterialUnits,
    PropertySource, ResultUnits, SectionProperties, SectionUnits, demand_ratio,
)
from jym_structural.design.steel import steel_flexural_yield_capacity

material = MaterialProperties(
    name="synthetic steel", fy=250, fu=400, elastic_modulus=200000,
    shear_modulus=77000, units=MaterialUnits(stress="MPa"),
)
section = SectionProperties(
    name="synthetic section", area=100, ix=900, iy=400, sx=7, sy=11,
    zx=1_000_000, zy=250_000, rx=3, ry=2, j=10, cw=0,
    units=SectionUnits(length="mm"),
)
capacity = steel_flexural_yield_capacity(
    material, section, component="m3", section_axis="x", factor=0.9,
    member_id="12", source=PropertySource(kind="manual", name="example calculation"),
)
assert isinstance(capacity, CapacityValue)
assert capacity.value == 225_000_000  # 0.9 * 250 * 1_000_000
assert capacity.unit == "N*mm"
y_capacity = steel_flexural_yield_capacity(
    material, section, component="m2", section_axis="y", factor=1.0,
)
assert y_capacity.value == 62_500_000

demand = ForceExtreme(
    member_id="12", component="m3", kind="absolute",
    source=FrameForces(
        object_id="12", station=0, element_id="e1", element_station=0,
        load_case="synthetic", step_num=0, m3=-168_750_000,
    ),
    units=ResultUnits(force="N", length="mm"),
)
check = demand_ratio(demand, capacity)
assert check.ratio == 0.75 and check.passes
assert check.demand.value == -168_750_000
```

The existing DemandCheck rules remain exact component/unit/member equality
(member equality applies when capacity.member_id is supplied). Mismatches fail
explicitly; DemandCheck never converts this calculated capacity.

## Limits and verification

**This calculator produces only Fy × Z × factor. It does not determine whether
using Z is applicable under a particular standard.** It is not complete AISC,
E.090, LRFD or ASD design. It checks no compactness, local buckling, lateral
torsional buckling (LTB), slenderness or other stability conditions. It computes
no shear, axial, torsional, interaction or serviceability resistance/checks.

No Core model, adapter, SAP2000 contract, CSI API, solver, MCP or UI changes are
required. Importing design.steel loads no adapters. A0.7 is outside this block.

Validation: 44 new tests, **481 total passed**, retaining all 437 previous tests.
One existing pytest cache-directory permission warning remains. `ruff check src
tests` and `git diff --check` pass. The synthetic example above was also executed.
