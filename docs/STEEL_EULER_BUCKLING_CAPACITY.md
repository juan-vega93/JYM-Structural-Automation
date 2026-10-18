# Steel Euler elastic buckling capacity (A0.8)

This service calculates ideal elastic Euler buckling in
`src/jym_structural/design/steel/buckling.py`. It depends on neutral Core data
without changing Core contracts or adapters. It returns the existing CapacityValue.

## Public API and inputs

```python
from jym_structural.design.steel import steel_euler_buckling_capacity

# steel_euler_buckling_capacity(
#     material: MaterialProperties, section: SectionProperties, *,
#     axis: Literal["x", "y"], length: float, k_factor: float, factor: float,
#     member_id: str | None = None, source: PropertySource | None = None,
# ) -> CapacityValue
```

Axis, physical length L, effective-length coefficient K and capacity factor are
all required. Axis x selects `section.rx`; axis y selects `section.ry`. No minimum
radius, critical axis, member length or support condition is inferred. The caller
supplies K without lookup tables. No local member-axis orientation is inferred.

L, K and factor must be finite and strictly positive. Integers and floats are
accepted; zero, negatives, NaN, infinities, booleans, strings and None fail strict
Pydantic validation. Factor has no implied phi, Omega, LRFD or ASD interpretation.
The caller is responsible for its meaning and provenance.

Material and section types are checked and their existing instances revalidated,
including unchecked `model_copy(update=...)` changes and nested units. The full
Core property contracts still apply, although only `material.elastic_modulus`,
`section.area` and the selected radius determine Euler capacity. There is no
grade/section-family restriction or material-reference resolution.

## Equations and units

```text
radius = section.rx if axis == "x" else section.ry
slenderness = k_factor * length / radius
Fe = math.pi**2 * material.elastic_modulus / slenderness**2
Pcr = Fe * section.area
capacity = factor * Pcr
```

Only exact `MaterialUnits.stress="MPa"` and `SectionUnits.length="mm"` are
supported. **The scalar length uses SectionUnits.length, therefore mm in A0.8.**
There is no second length-unit parameter. E is N/mm², A is mm², L and r are mm,
slenderness is dimensionless, Fe is N/mm² and the output is **N**. No additional
numeric scaling, conversion to kN or general unit parser is applied.

Unsupported combinations (MPa/m, ksi/in, kgf/cm²/cm, including case/whitespace
mismatches) raise ValueError with `Unsupported unit combination`. This is a support
policy, not an assertion that those pairs are physically invalid. Invalid axis
also raises ValueError; wrong property object types raise TypeError. Invalid
scalar/property/output fields raise Pydantic ValidationError, a ValueError subclass.

Floating-point intermediates (slenderness, its squared denominator, Fe and Pcr)
are validated as positive finite values before reuse. Squaring uses multiplication
so overflow is rejected through finite validation; a zero denominator is rejected
before division. CapacityValue rejects a nonfinite or zero final product as well.
Extreme inputs that overflow/underflow an intermediate are rejected rather than
rearranged or silently clamped, even if a different arithmetic order might succeed.

## Output and provenance

The frozen CapacityValue contains component p, positive calculated magnitude,
unit N and stable `limit_state="steel_euler_buckling"`. Section and material names
are copied exactly; optional member_id and caller-supplied PropertySource are
preserved exactly. Absent provenance stays None. Neither material nor section
provenance is substituted for calculation provenance and no standard is invented.

The function is pure and repeatable. Inputs are not modified. The output supports
JSON round trips and frozen assignment behavior. Keep the input properties,
axis, L, K and factor with the calling workflow for a full recomputation record;
the unchanged CapacityValue does not store calculation inputs or intermediates.

## Synthetic example and DemandCheck

This is illustrative supplied data, not a real profile or validated catalog.

```python
import math
from jym_structural.core import (
    ForceExtreme, FrameForces, MaterialProperties, MaterialUnits, PropertySource,
    ResultUnits, SectionProperties, SectionUnits, demand_ratio,
)
from jym_structural.design.steel import steel_euler_buckling_capacity

material = MaterialProperties(
    name="synthetic steel", fy=250, fu=400, elastic_modulus=200000,
    shear_modulus=77000, units=MaterialUnits(stress="MPa"),
)
section = SectionProperties(
    name="synthetic section", area=10000, ix=900, iy=400, sx=7, sy=11,
    zx=1000, zy=250, rx=100, ry=50, j=10, cw=0, units=SectionUnits(length="mm"),
)
capacity = steel_euler_buckling_capacity(
    material, section, axis="x", length=3000, k_factor=1.0, factor=1.0,
    member_id="12", source=PropertySource(kind="manual", name="example calculation"),
)
expected = math.pi**2 * 200000 * 10000 / (1.0 * 3000 / 100)**2
assert math.isclose(capacity.value, expected)
assert capacity.unit == "N"
# slenderness = 30; Fe approximately 2193.245 MPa; Pcr approximately 21932454.225 N.

for sign in (1, -1):
    demand = ForceExtreme(
        member_id="12", component="p", kind="absolute",
        source=FrameForces(
            object_id="12", station=0, element_id="e1", element_station=0,
            load_case="synthetic", step_num=0, p=sign * capacity.value / 2,
        ),
        units=ResultUnits(force="N", length="mm"),
    )
    check = demand_ratio(demand, capacity)
    assert math.isclose(check.ratio, 0.5) and check.passes
```

DemandCheck's existing exact component/unit/member compatibility rules apply.
It compares magnitudes and accepts both signs; Euler represents compressive
instability, so a numeric comparison with positive demand does not establish
tension resistance. Neither the capacity DTO nor this block infers sign conventions.

## Independence and limitations

A0.7 calculates `steel_axial_yielding`; A0.8 calculates `steel_euler_buckling`.
These mechanisms remain independent. There is no automatic axis selection,
`min(yield, buckling)` or governing-capacity service. Fe is **not capped at Fy**;
Euler is returned even when Fe exceeds Fy, as in the example above.

This is ideal elastic Euler only, not complete compression design under AISC,
E.090, LRFD or ASD. No inelastic curve, normative Fcr equation, yield-based
transition, local buckling, imperfection or residual-stress adjustment is included.
The caller must assess applicability; no physical/code applicability verdict is
produced. There are no general conversions, solver calls, MCP/UI or A0.9 features.

## Validation record

94 new tests cover axes and formula, strict inputs, units, unchecked property
copies, overflow/underflow, purity, frozen JSON outputs and DemandCheck. Scaling
tests check doubling L or K divides capacity by four, doubling r multiplies it
by four, and E/A scale linearly, on both axes. Independent variations of Fy/Fu/G,
Poisson ratio and unused section properties do not change Euler. Import tests
confirm no adapters or comtypes load.

**624 tests pass**, retaining all 530 previous tests. One existing pytest cache
permission warning remains. `ruff check src tests` and `git diff --check` pass.
The documented example was executed successfully.
