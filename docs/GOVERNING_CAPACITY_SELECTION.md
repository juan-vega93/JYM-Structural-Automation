# Governing capacity selection (A0.9)

`core/capacity_selection.py` selects among existing neutral CapacityValue objects.
This is a Core operation, independent of steel calculations, solvers and standards:

```text
Calculators -> CapacityValue -> governing_capacity -> DemandCheck
```

## Public API and rule

```python
from jym_structural.core import governing_capacity

# governing_capacity(capacities: Iterable[CapacityValue]) -> CapacityValue
```

Select the **minimum capacity.value** from the supplied compatible candidates.
Every existing ForceComponent is supported: p, v2, v3, t, m2, m3. There is no sign
handling because capacity magnitudes are positive. A single candidate is valid
and returned unchanged. Empty input raises ValueError with
`At least one capacity is required`. No None result or extra DTO is introduced.

The Iterable is consumed once, so generators are supported. The function validates
every candidate, including those larger than the current minimum. Each element
must be a CapacityValue instance; dictionaries and other objects raise TypeError.
Each instance's round-trip representation is revalidated to reject invalid unchecked
copies (zero/negative/NaN values, blank labels, invalid nested source, etc.). The
validated data is used for comparison, but the original winning instance is returned.
Invalid fields raise Pydantic ValidationError, a ValueError subclass.

## Exact compatibility

All candidates must agree on every field below; the error identifies the field.

| Field | Requirement |
| --- | --- |
| component | Exactly equal |
| unit | Exactly equal label; N differs from kN |
| member_id | All None or all exactly equal non-null IDs |
| section_name | All None or all exactly equal non-null names |
| material_name | All None or all exactly equal non-null names |

For optional references, mixing None with a supplied value fails. Different values
fail too. No trimming, case normalization, association inference or reference
resolution occurs. No unit conversion or grouping is performed; each call handles
one homogeneous candidate set.

`limit_state` and `source` may differ. The selected original retains its mechanism
label, references and provenance without mutation; it is never relabelled as
`governing`. There is no source/provider priority with engineering meaning.

## Ties and determinism

Ascending selection key:

```text
(capacity.value, capacity.limit_state, canonical_source_json)
```

Identity fields are already equal and need no further ranking. Canonical source
JSON serializes source.model_dump(mode="json"), or None, with sorted keys, compact
separators and ASCII escapes. Absent source serializes as `null`. This is a lexical
convention only: null sorts before source objects; source objects compare their
canonical data. Labels and source name/version strings remain uninterpreted.

No object ID, hash or input-order field appears in the key. All permutations of
distinct data produce the same winning object. Exact duplicates are accepted:
their complete data and key are indistinguishable, so either original duplicate
instance may be returned. Logical output remains identical; selecting a particular
identity among indistinguishable copies independently of order would require an
identity/order tie break, which this operation deliberately does not introduce.

Selection does not sort the input collection or mutate any object. Frozen behavior
and JSON serialization remain unchanged. Returning the original is intentional;
there is no new snapshot or CapacityValue copy in the returned result.

## Caller controls applicability

**governing_capacity() does not determine which limit states are applicable.**
The caller controls the candidate set. Supplying yielding and Euler compares only
those two; supplying only yielding compares only yielding. No mechanisms are
added automatically and no calculator is imported or invoked. Selecting the smaller
of yielding/Euler is not a complete steel compression design claim. There is no
AISC/E.090 interpretation or design-standard applicability assessment.

## Synthetic axial example and DemandCheck

These directly supplied illustrative capacities require no calculator invocation.

```python
from jym_structural.core import (
    CapacityValue, ForceExtreme, FrameForces, PropertySource, ResultUnits,
    demand_ratio, governing_capacity,
)

references = dict(member_id="12", section_name="synthetic section", material_name="synthetic steel")
yielding = CapacityValue(
    component="p", value=2_500_000, unit="N", limit_state="steel_axial_yielding",
    source=PropertySource(kind="manual", name="supplied yielding"), **references,
)
euler = CapacityValue(
    component="p", value=1_800_000, unit="N", limit_state="steel_euler_buckling",
    source=PropertySource(kind="imported", name="supplied Euler"), **references,
)
governing = governing_capacity([yielding, euler])
assert governing is euler
assert governing.limit_state == "steel_euler_buckling"
demand = ForceExtreme(
    member_id="12", component="p", kind="absolute",
    source=FrameForces(
        object_id="12", station=0, element_id="e1", element_station=0,
        load_case="synthetic", step_num=0, p=-900_000,
    ),
    units=ResultUnits(force="N", length="mm"),
)
check = demand_ratio(demand, governing)
assert check.ratio == 0.5 and check.passes
```

DemandCheck is unchanged and applies its existing demand/capacity compatibility
and magnitude-ratio rules to the selected capacity.

## Synthetic flexural example

`future_ltb` is a supplied test label, not an implemented LTB calculation.

```python
from jym_structural.core import CapacityValue, governing_capacity

yielding = CapacityValue(
    component="m3", value=200_000_000, unit="N*mm", limit_state="steel_flexural_yielding",
)
future = CapacityValue(
    component="m3", value=150_000_000, unit="N*mm", limit_state="future_ltb",
)
assert governing_capacity(c for c in [yielding, future]) is future
```

## Verification and scope

51 new tests cover selection, permutations and source ties, duplicates, all six
components, strict identity/unit policies, generators, invalid unchecked copies,
purity, original-instance return and synthetic axial/flexural integration.
Cold Core import and execution load no design, adapters or comtypes.

**675 tests pass**, retaining all 624 previous tests. One existing pytest cache
permission warning remains. `ruff check src tests` and `git diff --check` pass.
Both examples above were executed successfully. CapacityValue, DemandCheck,
calculators and adapters are unchanged. No calculations, unit conversions,
normative semantics, new capacity DTOs or A0.10 are introduced.
