# Structural Core: neutral capacity abstractions (A0.5)

A0.4 material/section properties describe supplied physical data. `CapacityValue`
represents an already calculated or supplied available capacity. A design-standard
calculation would produce such a result; this block does not implement that
calculation, resistance factors, interactions or formulas from AISC/E.090.

## Public model

Import `CapacityValue`, `PropertySource`, `DemandCheck` and `demand_ratio` from
`jym_structural.core`. Capacity models live in `core/capacity_models.py`, operations
remain in `core/result_processing.py`. The single shared `ForceComponent` alias
lives in `core/models.py` to avoid a dependency cycle with result models.

| Field | Contract |
| --- | --- |
| component | Existing ForceComponent: p, v2, v3, t, m2, m3 |
| value | Finite, strictly positive magnitude; no resistant sign |
| unit | Explicit nonblank label, preserved exactly |
| limit_state | Nonblank free-form label, preserved without interpretation |
| member_id | Optional nonblank exact member identifier |
| section_name / material_name | Optional nonblank references, not resolved |
| source | Optional existing frozen PropertySource; absent if unknown |

`PropertySource` supports manual, catalog, solver, bim and imported origins,
with optional name/version. It identifies provenance without inventing a source
or hardcoding an engine. Metadata is retained in nested check JSON. No additional
method or capacity-type hierarchy is introduced; neither is needed for this
comparison. Section/material references impose no catalog or property dependency.

CapacityValue is frozen, strictly validated, rejects unknown fields, supports JSON
round trips and deep copies, and contains no mutable collections. Optional strings
may be None; supplied blank or whitespace-only strings fail validation. Labels are
not trimmed or parsed.

## Compatibility and ratio

```python
def demand_ratio(demand: ForceExtreme, capacity: CapacityValue) -> DemandCheck: ...
```

The scalar capacity API has been replaced. Both the function and direct
`DemandCheck` construction validate:

- `demand.component == capacity.component`;
- `demand.unit == capacity.unit`, by exact string equality;
- `capacity.member_id == demand.member_id` when capacity.member_id is not None.

P/V2/V3 demand units derive from ResultUnits.force; T/M2/M3 derive from
ResultUnits.moment. No dimensional parser is added: standalone capacities retain
their supplied unit label, and compatibility is enforced against the demand.
`kgf*m` differs from `kN*m`; `N*m` differs from `kN*mm`; even `kN*m` differs from
`kN·m`. Whitespace and case remain significant. There is no conversion or silent
normalization. A capacity without member_id can be reused across members;
section_name/material_name are preserved without attempting reference resolution.

`ratio = abs(demand.value) / capacity.value` and `passes = ratio <= 1.0` are
computed, read-only properties. Floating-point overflow is rejected rather than
returning an infinite ratio. The signed demand, complete source row and units
remain available; the capacity remains positive. This numeric comparison supplies
no code-compliance conclusion beyond the supplied demand and capacity.

## Neutral example and migration

```python
from jym_structural.core import (
    CapacityValue, ForceExtreme, FrameForces, PropertySource, ResultUnits, demand_ratio,
)

demand = ForceExtreme(
    member_id="12", component="m3", kind="absolute",
    source=FrameForces(
        object_id="12", station=0, element_id="e1", element_station=0,
        load_case="case", step_num=0, m3=-150,
    ),
    units=ResultUnits(force="kN", length="m"),
)
capacity = CapacityValue(
    component="m3", value=200, unit="kN*m", limit_state="manual_capacity",
    member_id="12", source=PropertySource(kind="manual", name="engineering review"),
)
check = demand_ratio(demand, capacity)
assert check.ratio == 0.75 and check.passes
assert check.demand.value == -150
assert check.capacity.source.name == "engineering review"
```

Replace previous numeric capacity arguments with explicit CapacityValue instances,
including the component, unit and supplied limit-state label. No parallel scalar
compatibility API remains.

## Snapshots and scope

DemandCheck detaches and revalidates both inputs, including capacity provenance.
Functions do not mutate their inputs. Capacity and its source are frozen; existing
nested FrameForces/ResultUnits remain mutable for compatibility, so treat check
outputs as value snapshots and reconstruct them for intentional changes. A source
edit after constructing a check cannot rewrite that check's snapshot.

A0.2 extrema/envelopes retain their processing and provenance rules. A0.3 checks
now consume labelled capacities, while A0.4 properties remain separate. Tests
cover every component, invalid magnitudes/labels, provenance, optional references,
exact compatibility, ratio boundaries, JSON, frozen values and detached snapshots.
All previous regressions run, including cold Core import without adapters.
No adapter, SAP2000 contract or CSI operation is changed. No external application,
analysis, solver API, resistance calculation, unit conversion or A0.6 is added.

Validation: 49 new tests plus the 388 retained/migrated tests, **437 passed**.
Pytest reports one existing cache-directory permission warning. `ruff check src
tests` and `git diff --check` pass. Both this example and the migrated example in
`STRUCTURAL_CORE_RESULTS.md` were executed successfully.
