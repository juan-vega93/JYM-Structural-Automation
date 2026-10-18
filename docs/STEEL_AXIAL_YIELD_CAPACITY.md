# Steel axial yield capacity (A0.7)

The second calculated capacity consumes supplied MaterialProperties and
SectionProperties and returns the existing frozen CapacityValue. The service
lives in `src/jym_structural/design/steel/axial.py`, outside the neutral Core.

## API and formula

```python
from jym_structural.design.steel import steel_axial_yield_capacity

# steel_axial_yield_capacity(
#     material: MaterialProperties, section: SectionProperties, *,
#     factor: float, member_id: str | None = None,
#     source: PropertySource | None = None,
# ) -> CapacityValue
```

The only capacity formula is **factor × material.fy × section.area**.
Fu, E, G, inertias, radii and section moduli do not determine the capacity. All
required properties still undergo their existing Core validation. No grade or
section family is inferred or required, and material references are not resolved.

Factor is required, finite and strictly positive. Integer values such as 1 are
accepted, as are floats such as 1.0 and 0.9. Zero, negatives, NaN, either infinity,
booleans, strings and None are rejected by strict Pydantic validation. Factor has
no implied phi, Omega, LRFD or ASD meaning; its origin belongs to the caller.

## Units and validation

Only the exact pair `MaterialUnits.stress="MPa"` and
`SectionUnits.length="mm"` is supported. MPa = N/mm², and supplied area is mm²,
so the result is **N**, with no additional scale factor or conversion to kN.

Other combinations raise ValueError with `Unsupported unit combination`, including
MPa/m, ksi/in and kgf/cm²/cm. This describes unsupported inputs, not physical
invalidity. Case and whitespace are significant. There is no parser or silent
normalization. Axial and flexural calculations share only small private factor
and MPa/mm validation helpers in `design/steel/_validation.py`.

Wrong material/section object types raise TypeError. Existing property instances
are revalidated before calculation, including nested units and unchecked values
introduced through `model_copy(update=...)`. Invalid property/factor/output fields
raise Pydantic ValidationError, a ValueError subclass. Nonfinite and zero products
caused by floating-point overflow/underflow fail CapacityValue validation.

## Output, provenance and purity

The result is exactly a CapacityValue with:

- `component="p"`, positive calculated value, `unit="N"`;
- `limit_state="steel_axial_yielding"`;
- section_name and material_name copied exactly from the supplied properties;
- caller-supplied optional member_id and PropertySource preserved exactly.

An absent source stays None. Material or section provenance is not substituted
for calculation provenance; no normative source is invented. The function does
not mutate material, section or source and is repeatable. Output remains frozen
and supports JSON round trips. The Core and DemandCheck contracts are unchanged.
For full recomputation history, retain the input properties and explicit factor
with the calling workflow; CapacityValue does not store calculation inputs.

## Synthetic example and DemandCheck

These are illustrative supplied values, not a real profile or verified catalog.

```python
from jym_structural.core import (
    CapacityValue, ForceExtreme, FrameForces, MaterialProperties, MaterialUnits,
    PropertySource, ResultUnits, SectionProperties, SectionUnits, demand_ratio,
)
from jym_structural.design.steel import steel_axial_yield_capacity

material = MaterialProperties(
    name="synthetic steel", fy=250, fu=400,
    elastic_modulus=200000, shear_modulus=77000,
    units=MaterialUnits(stress="MPa"),
)
section = SectionProperties(
    name="synthetic section", area=10_000, ix=900, iy=400,
    sx=7, sy=11, zx=1_000_000, zy=250_000, rx=3, ry=2, j=10, cw=0,
    units=SectionUnits(length="mm"),
)
capacity = steel_axial_yield_capacity(
    material, section, factor=0.9, member_id="12",
    source=PropertySource(kind="manual", name="example calculation"),
)
assert isinstance(capacity, CapacityValue)
assert capacity.value == 2_250_000  # 0.9 * 250 * 10_000
assert capacity.unit == "N"
assert steel_axial_yield_capacity(material, section, factor=1.0).value == 2_500_000

for axial_force in (1_125_000, -1_125_000):
    demand = ForceExtreme(
        member_id="12", component="p", kind="absolute",
        source=FrameForces(
            object_id="12", station=0, element_id="e1", element_station=0,
            load_case="synthetic", step_num=0, p=axial_force,
        ),
        units=ResultUnits(force="N", length="mm"),
    )
    check = demand_ratio(demand, capacity)
    assert check.ratio == 0.5 and check.passes
    assert check.demand.value == axial_force
```

DemandCheck compares abs(demand.value) against the positive capacity. Both signs
can use the same magnitude; this makes no normative tension/compression distinction.
Component must equal p, unit must equal N exactly, and member must match when the
capacity supplies one. Member, component and unit mismatches remain errors.

## Limitations and validation record

This is only axial yielding with supplied area, not complete AISC, E.090, LRFD
or ASD design. Comparing a negative demand does **not** constitute a compression
buckling check. No buckling, KL/r, Euler, Fe, Fcr, effective lengths or compression
curves are calculated. No fracture, rupture, net/effective area, block shear or
Fu-based resistance is calculated. There are no general unit conversions.

No Core or adapter changes, solver operations, MCP, UI or A0.8 are introduced.
The existing flexural calculator remains exported. Cold-import tests verify that
design.steel loads neither adapters nor comtypes.

Validation: **49 new tests, 530 total passed**, retaining the 481 previous tests.
One existing pytest cache permission warning remains. `ruff check src tests` and
`git diff --check` pass. The documented numerical example was executed successfully.
