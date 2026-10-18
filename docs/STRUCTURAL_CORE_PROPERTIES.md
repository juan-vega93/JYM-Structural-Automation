# Neutral material and section properties (A0.4)

A0.4 separates **material data**, **section geometry** and **design capacities**.
Only the first two are represented. These value objects contain supplied data;
they do not calculate section resistance or assign capacities to demand checks.
No adapters, solver SDKs, standards, catalogs, extraction or conversion logic are
introduced. The implementation is in `core/property_models.py`.

## Public models

```python
from jym_structural.core import (
    MaterialProperties, MaterialUnits, SectionProperties, SectionUnits, PropertySource,
)
```

| Model | Data |
| --- | --- |
| MaterialProperties | name, fy, fu, elastic_modulus (E), shear_modulus (G), optional poisson_ratio, units, optional source |
| MaterialUnits | required stress label for Fy, Fu, E and G |
| SectionProperties | name, area (A), ix/iy, sx/sy, zx/zy, rx/ry, j, cw; optional d/bf/tf/tw, section_type, material_name, source; required units |
| SectionUnits | required length label, with derived dimensional properties |
| PropertySource | required kind; optional name and version |

Names are identities, preserved exactly as supplied. No GUIDs, registry or database
are created. `material_name` is an optional string reference, not an embedded
MaterialProperties object. A0.4 does not resolve this reference or require an
external material collection. `section_type` is a free neutral label (such as I,
HSS, Channel, Angle or Custom), not a hierarchy or provider enum.

## Validation and supplied values

All five models use frozen, strict Pydantic configuration. Unknown fields are
rejected, as are blank required names/unit labels. Supplied optional string labels
must also be nonblank; None means absent. No automatic trimming or unit parsing
occurs. Numeric strings and booleans are not physical numeric inputs; ordinary
integers are accepted as float values.

Material data requires explicit, finite, positive Fy, Fu, E and G, with Fu >= Fy.
All four are required; none receives a guessed default. Optional Poisson ratio
uses the conventional structural-material range **0 <= nu < 0.5** and must be finite.
This does not cover auxetic materials. The model never derives G from E/nu, nu
from E/G, or enforces an isotropic relation that the caller did not supply.

Density is deliberately omitted: a mass/volume unit DTO would add an unnecessary
dimension to this block. A supplied density field is rejected rather than stored
as an ambiguous bare number. No density defaults are introduced.

Section properties are all required and finite. A, Ix, Iy, Sx, Sy, Zx, Zy, rx, ry
and J must be > 0; **Cw may be zero**, but not negative. Supplied dimensions
d, bf, tf and tw must be finite and > 0; all default to None when absent. No
type-specific dimension relationships are imposed. The Core does not calculate
missing properties, infer section shape or assert geometric consistency between
separately supplied A/I/r/S/Z values.

## Axes

The x/y labels in Ix/Iy, Sx/Sy, Zx/Zy and rx/ry describe the section catalog's
neutral section axes, typically its principal-axis pair. A source must establish
which axes its values describe. They are **not** automatically the member's local
2/3 axes. The model does not decide which axis is strong/weak from the name or
relative magnitudes. In particular, it does not assume M3 maps to Sx or M2 to Sy.
Catalog-to-member orientation/mapping remains a separate future block.

## Units: explicit labels, no conversion

MaterialUnits.stress is an explicit, open-ended, nonblank string, e.g. MPa, ksi or
kgf/cm^2. All four stress/modulus values use that same label. Its spelling is not
normalized and it is not interpreted as a conversion request.

SectionUnits stores **one length label**; the derived properties always come
from that label:

| Property | For length="mm" | Applies to |
| --- | --- | --- |
| length | mm | rx/ry, d/bf/tf/tw |
| area | mm^2 | A |
| inertia | mm^4 | Ix/Iy and J |
| section_modulus | mm^3 | Sx/Sy and Zx/Zy |
| warping | mm^6 | Cw |

These are read-only Python properties. The canonical JSON contains only
`{"length": "mm"}`, so derived labels cannot contradict their base label and
round-trip JSON needs no duplicate dimensional fields. Passing an independent
`area`, `inertia`, `section_modulus` or `warping` argument is rejected. No closed
unit list, complex expression parser or unit conversion is implemented. The caller
must provide an actual length label and values consistent with the declared units.

## Provenance

PropertySource.kind is one of **manual, catalog, solver, bim, imported**. Optional
name/version identify a source without hardcoding a provider. The entire source
may be None when not known; the Core does not invent provenance. Provenance applies
to the supplied property set as a whole, not to each number separately.

Tests use a synthetic I-300 fixture with illustrative rectangular-I dimensions
and approximate A/I/S/Z/r values. J and Cw are synthetic placeholders. They are
explicitly marked manual test data, **not validated catalog or official profile
properties**. This block imports no catalog data.

## Compatibility and value-object behavior

The existing `Section(name, material, family)` is unchanged and remains the
lightweight inventory/mapping model used by adapters. SectionProperties is a
separate physical-property DTO; it neither replaces Section nor adds fields to
StructuralModel. Material and section geometry remain separate from the prior
numeric DemandCheck capacity, which still comes explicitly from its caller.

All new objects and their nested unit/provenance objects are frozen. They consist
of immutable primitives and frozen DTOs, with no mutable lists or dictionaries.
JSON round trips and `model_copy(deep=True)` preserve values. As with Pydantic in
general, `model_copy(update=...)` and `model_construct` bypass validation and must
not be used to accept untrusted updates. Use a new validated object instead:

```python
changed = MaterialProperties.model_validate({**material.model_dump(), "fy": 300})
```

Nested property DTO instances are revalidated when supplied to another property
model. Frozen means ordinary attribute assignment is rejected; it is not a
security boundary against deliberate validation bypass.

## Small synthetic example

```python
from jym_structural.core import (
    MaterialProperties, MaterialUnits, SectionProperties, SectionUnits, PropertySource,
)

source = PropertySource(kind="manual", name="illustrative data", version="1")
material = MaterialProperties(
    name="steel-example", fy=250, fu=400,
    elastic_modulus=200000, shear_modulus=77000, poisson_ratio=0.3,
    units=MaterialUnits(stress="MPa"), source=source,
)
section = SectionProperties(
    name="synthetic-section", area=100, ix=900, iy=400,
    sx=300, sy=200, zx=400, zy=300, rx=3, ry=2, j=10, cw=0,
    section_type="Custom", material_name=material.name,
    units=SectionUnits(length="mm"), source=source,
)
assert section.d is None
assert section.units.area == "mm^2"
assert section.units.inertia == "mm^4"
assert section.units.section_modulus == "mm^3"
assert section.units.warping == "mm^6"
assert SectionProperties.model_validate_json(section.model_dump_json()) == section
```

The example is not a standard material grade or a catalog profile. Its values
are supplied illustrative data, with no computed strength or resistance claim.

## Scope and verification

Tests cover all positive/finite material and section fields, strength ordering,
Poisson bounds, Cw=0, absent dimensions, units and derived powers, optional
provenance, strict errors, frozen nested models, copying, validated updates and
JSON round trips. A fresh interpreter test verifies that the public Core types
load without importing any adapter. All earlier tests remain active.

No adapters or their contracts are changed. No external application is accessed.
There are no capacities, standards, resistance factors, axis mapping, conversions,
slenderness/buckling checks, catalogs, extraction, databases, MCP or UI in A0.4.

Validation: **114 new tests, 388 total passed**, including all 274 prior tests.
There is one existing pytest cache permission warning. `ruff check src tests` and
`git diff --check` pass. The documented synthetic example also ran successfully.
