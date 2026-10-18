# Structural Core: result processing and basic checks (A0.2/A0.3)

This layer operates on neutral AnalysisResult/FrameForces/ResultUnits only. It does
not import adapters, proprietary SDKs or transports, call a solver, select output,
or interpret source-specific case names. Existing B1.1–B1.5 models and adapters
remain unchanged. Geometry snapshots do not acquire result-processing behavior.

## Public API

Import these names from `jym_structural.core`:

```python
component_extreme(result, component, *, kind="max")  # kind must be explicit: min/max
component_envelope(result, component)               # independent minimum and maximum
absolute_extreme(result, component)                 # largest magnitude, original sign
demand_ratio(demand, capacity)                      # DemandCheck
```

The first line illustrates a call with kind="max", not an implicit default.
Only `ForceComponent = Literal["p", "v2", "v3", "t", "m2", "m3"]` is supported.
Unsupported components/kinds fail at runtime as well as being restricted in typing.
Functions live in `core/result_processing.py`; output models live separately in
`core/result_models.py`.

| Model | Meaning |
| --- | --- |
| ForceExtreme | member_id, component, kind (min/max/absolute), complete source FrameForces and ResultUnits |
| ForceEnvelope | one component with independent minimum and maximum ForceExtreme rows |
| DemandCheck | traceable demand ForceExtreme and CapacityValue, computed ratio and passes |

`ForceExtreme.value` is computed directly from its source component. `unit` is
computed from the same component and ResultUnits. These are serialized fields,
without independent writable copies that could diverge from the source.
ForceEnvelope checks matching components, kinds, member and units, and min <= max.
All new models support Pydantic JSON serialization/deserialization.

## Traceability and input policy

Each extreme retains the **whole original row**, including the other force
components, not a fictitious row assembled from component maxima. It preserves
member/object ID, object station (`station`), element ID, element station,
load_case label, step_type, step_num and full units. Signs and local axes do not
change; endpoints, directions, case/combination categories and step semantics are
not inferred.

Every input row is validated, including non-controlling rows. An operation fails
instead of skipping rows when:

- forces is empty, units are absent, or force/length units are blank;
- member_id is blank or a row's object_id differs from member_id;
- object_id, element_id or load_case is absent/blank;
- station, element_station, step_num or the **requested component** is None;
- numeric data is NaN/Inf or otherwise invalid for the existing Core row model.

`step_type=None` is a legitimate absence of a step type and is retained. A supplied
empty step_type is also preserved, not interpreted. Missing **unrequested** force
components remain None in the full source snapshot; they are not silently filled
or processed. Requesting an envelope for such a component fails. No ignore-missing
mode is provided. A row edited after initial construction is revalidated while
creating the detached snapshot, so prior Pydantic validation is not blindly trusted.

Invalid processing requests use ValueError (including Pydantic ValidationError for
invalid snapshot fields); a non-AnalysisResult input raises TypeError.

## Stable ties

For equal signed values, choose the ascending lexicographic provenance key:

```text
load_case
(step_type is not None, step_type or "")
step_num
station                 # object station
element_id
element_station
object_id
complete source-row JSON
```

Null step_type sorts before an empty string, then other strings sort normally.
The full serialization is a final deterministic tie breaker for rows whose primary
provenance and requested value coincide but other data differ (including signed
zero). Exact serialized duplicates produce indistinguishable outputs. No source-row
order is treated as a physical priority. All input permutations give the same
output for the same data.

For absolute extremes, first maximize abs(value), then choose the smaller signed
value: **-x wins over +x** at equal magnitude. Remaining ties use the provenance
key above. This is a deterministic convention, not an engineering inference.
The output keeps its original sign: -18 beats +15 and remains -18.

An envelope reports two signed bounds, with a real source for each. An absolute
extreme reports just one controlling-magnitude source. Neither remaps axes,
changes force correspondence, computes vector magnitudes or combines components.

## Units and basic demand ratio

No unit conversion occurs. P/V2/V3 use ResultUnits.force, T/M2/M3 use
ResultUnits.moment, and both stations use ResultUnits.length. The same full
ResultUnits context is carried in each detached extreme.

```text
capacity.value > 0 and finite
ratio = abs(demand.value) / capacity.value
passes = ratio <= 1.0
```

Since A0.5, capacity is a `CapacityValue`, replacing the former scalar API.
The Core requires matching components and exactly equal unit labels, plus matching
member IDs when capacity.member_id is supplied. It never converts or normalizes
units. Non-finite capacities and floating-point ratio overflow are rejected.
A negative demand retains its sign inside DemandCheck.demand even though the
ratio uses its magnitude. See `STRUCTURAL_CORE_CAPACITY.md` for the full contract.

This comparison applies no resistance factors, code provisions, interaction
equations or section resistance calculation. It makes no engineering assertion
beyond the numeric comparison supplied by the caller.

## Pure functions and snapshots

The input result, rows, units and list order are not modified. Each returned
extreme copies and revalidates its source and units; DemandCheck also detaches its
demand and capacity. Subsequent input edits cannot rewrite the returned provenance, and edits
to the returned source cannot alter the input.

The new outer DTOs are frozen, but existing nested FrameForces/ResultUnits objects
are **not deeply immutable**. Treat outputs as serialized value snapshots and do
not edit their nested objects. This preserves compatibility with the existing Core
without redesigning all its models as immutable. To intentionally change a snapshot,
construct and validate a new one rather than modifying its nested source.

## Small neutral example

```python
from jym_structural.core import (
    AnalysisResult, CapacityValue, FrameForces, ResultUnits,
    absolute_extreme, component_envelope, component_extreme, demand_ratio,
)

result = AnalysisResult(
    member_id="member",
    units=ResultUnits(force="kN", length="m"),
    forces=[
        FrameForces(object_id="member", station=3, element_id="e2", element_station=1,
                    load_case="B", step_type=None, step_num=0, m3=-18),
        FrameForces(object_id="member", station=0, element_id="e1", element_station=0,
                    load_case="A", step_type="Step", step_num=1, m3=15),
    ],
)

envelope = component_envelope(result, "m3")
assert envelope.minimum.value == -18
assert envelope.maximum.value == 15
assert component_extreme(result, "m3", kind="max").source.load_case == "A"
demand = absolute_extreme(result, "m3")
assert demand.value == -18
assert demand.source.element_station == 1
assert demand.unit == "kN*m"
capacity = CapacityValue(
    component="m3", value=24, unit="kN*m", limit_state="manual_capacity",
)
check = demand_ratio(demand, capacity)
assert check.ratio == 0.75
assert check.passes
print(check.model_dump_json(indent=2))
```

The example's missing P/V2/V3/T/M2 values are explicit and not used. Asking to
process any of those components fails strictly rather than returning an envelope.

## Scope and validation

Tests use small, explicit neutral datasets with positive, negative and zero values,
multiple labels/stations/elements/steps, same-value and opposite-sign ties. They
check permutations, provenance, unit preservation, strict failures, JSON round trips,
detached snapshots and ratios below/equal/above one. A fresh interpreter test
verifies that importing and executing the Core does not load any adapter.

No adapters, their contracts or their tests are modified. No external model is
opened or analyzed for this block. No displacements, reactions, shells, stresses,
serviceability, design standards, buckling, optimization, MCP or UI are implemented.

Validation for this block: 66 new tests, **274 total passed** (208 existing tests
retained), with one pytest cache permission warning. `ruff check src tests` and
`git diff --check` pass. The documented small example was also executed successfully.
