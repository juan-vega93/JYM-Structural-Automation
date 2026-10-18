# Design standard metadata and applicability context (A0.10)

`core/design_context.py` represents supplied metadata and explicit decisions.
It prepares neutral data for future standard-specific design workflows without
interpreting standards. Dependencies will point from those workflows to Core;
Core does not import design, calculators, adapters or proprietary APIs.

## Public models

Import these names from `jym_structural.core`:

| Model | Required fields | Optional fields/defaults |
| --- | --- | --- |
| DesignStandard | name, edition | method=None, jurisdiction=None, source=None |
| ApplicabilityDecision | limit_state, applicable | reason=None, source=None |
| DesignContext | standard: DesignStandard | applicability: tuple[ApplicabilityDecision, ...] = () |

Every model uses `frozen=True`, `strict=True`, `extra="forbid"` and
`revalidate_instances="always"`. Unknown fields are rejected. No mutable list or
dictionary is stored: applicability is a tuple, and strict Python construction
rejects lists. JSON arrays deserialize to tuples via Pydantic's JSON handling.

All string fields are nonempty and contain at least one non-whitespace character
when supplied. Values are preserved exactly: no trimming, case normalization,
edition parsing, method enumeration or jurisdiction lookup occurs. Edition can
be `2022`, `Rev 4` or `project edition`; numeric editions are not coerced to strings.
Name/edition existence or current validity is not verified. Method and jurisdiction
are open labels. Future limit states need no registered calculator.

`applicable` is a strict boolean. True and False are accepted; 1, 0, 1.0,
`"true"` and `"false"` are rejected. Reason is free text, preserved without
interpretation, or None when absent.

Each standard/decision can carry its own optional PropertySource. Sources may
differ and preserve supplied kind/name/version. An absent source stays None;
no material/section/capacity provenance or normative source is inferred.

## Decisions, duplicates and unknown states

DesignContext preserves the supplied decision order. Each exact limit_state may
appear only once. Conflicting and identical duplicates both fail with ValueError
(Pydantic ValidationError). `state`, `State` and ` state ` are distinct valid labels;
whitespace-only labels fail before uniqueness validation. No automatic conflict
resolution or sorting occurs.

An absent decision means **unknown / not supplied**. It never implies True or False.
The neutral helper performs only exact lookup:

```python
def applicability_for(
    context: DesignContext, limit_state: str,
) -> ApplicabilityDecision | None: ...
```

It requires a DesignContext instance (otherwise TypeError), validates a strict
nonblank limit-state string, revalidates the context, and returns the matching
decision or None. Query validation errors are Pydantic ValidationError, a
ValueError subclass. It does not mutate inputs, add decisions or infer defaults.
Its result is a validated value, with no original-instance identity guarantee.

## Revalidation, snapshots and JSON

Revalidation is applied at nested model boundaries, including PropertySource.
An unchecked standard copy with a blank name, decision copy with a nonboolean
applicable value or invalid nested source fails when constructing DesignContext.
Revalidating a context also rechecks uniqueness. Tests verify these behaviors
directly rather than assuming the configuration is sufficient.

Nested input model instances are revalidated into detached frozen values. All
fields reject assignment. JSON serialization/deserialization preserves exact
strings and decision order, and deep copies preserve equivalent values. As with
existing Core DTOs, model_copy(update=...) bypasses validation by itself: validate
before accepting untrusted updates.

## Supplied metadata example

The names and decisions below are illustrative caller data. They make no claim
that a particular decision is correct under the named standard.

```python
from jym_structural.core import (
    ApplicabilityDecision, DesignContext, DesignStandard, PropertySource,
    applicability_for,
)

standard = DesignStandard(
    name="AISC 360", edition="2022", method="LRFD", jurisdiction="US",
    source=PropertySource(kind="manual", name="Project design basis", version="Rev B"),
)
context = DesignContext(
    standard=standard,
    applicability=(
        ApplicabilityDecision(
            limit_state="steel_axial_yielding", applicable=True,
            reason="candidate supplied by steel workflow",
        ),
        ApplicabilityDecision(
            limit_state="steel_euler_buckling", applicable=False,
            reason="example decision supplied by caller",
            source=PropertySource(kind="imported", name="supplied decisions"),
        ),
        ApplicabilityDecision(
            limit_state="future_lateral_torsional_buckling", applicable=True,
        ),
    ),
)
assert applicability_for(context, "steel_axial_yielding").applicable is True
assert applicability_for(context, "steel_euler_buckling").applicable is False
assert applicability_for(context, "missing") is None
assert applicability_for(context, "Steel_Euler_Buckling") is None
assert DesignContext.model_validate_json(context.model_dump_json()) == context
```

## Relationship to governing selection and future design

DesignContext records which candidates the caller considers applicable.
`governing_capacity()` only compares the candidate set it receives. A0.10 does
not connect them automatically: there is no filtering, applicable-capacity
selection or automatic governing calculation. CapacityValue, DemandCheck,
governing_capacity and the steel calculators are unchanged. Physical capacity
and design context remain separate; no fields are added to those contracts.

Future standard-specific layers may interpret these labels and compute their
own decisions, depending on Core. No standard subclasses, ranking, edition
precedence, hardcoded AISC/E.090 rules, normative equations or unit conversions
are introduced here. No internet verification of supplied editions is performed.
A0.11 and workflow orchestration remain outside this block.

## Verification

66 new tests cover strict labels/bools, sources, unknown/future states, duplicate
decisions, preserved order, frozen fields, detached nested values, unchecked-copy
revalidation, query behavior, deep copies and JSON round trips. Cold Core import
and query load neither design/calculators, adapters nor comtypes.

**741 tests pass**, retaining all 675 previous tests. One existing pytest cache
permission warning remains. `ruff check src tests` and `git diff --check` pass.
The documented example above was executed successfully.
