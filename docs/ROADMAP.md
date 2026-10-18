# Roadmap

## Track A — Structural Core (parallel)

### A0.1 — Domain skeleton
- ModelInfo
- Member
- Section
- FrameForces
- AnalysisResult
- stable JSON serialization

### A0.2 — Result processing and traceable envelopes
- explicit ResultUnits context without unit conversion
- signed component extrema, min/max envelopes and absolute extrema
- preserve full object/element station, case label and step provenance
- deterministic ties, strict missing-value validation and pure Core functions

### A0.3 — Basic demand checks
- traceable demand/capacity ratio using caller-supplied positive capacity
- abs(demand)/capacity; passes when ratio <= 1
- no design standards, resistance factors, section capacity or interactions

See `docs/STRUCTURAL_CORE_RESULTS.md` for the public API and policies.
Deflection, serviceability and code-based design remain outside this block.

### A0.4 — Neutral Materials & Section Properties
- immutable material, section, unit and provenance value objects
- explicit supplied Fy/Fu/E/G, optional conventional Poisson ratio
- finite section properties and optional dimensions, without capacity calculations
- dimensional section units derived from one length label; no conversion
- catalog x/y axes remain unmapped to member local axes

See `docs/STRUCTURAL_CORE_PROPERTIES.md`. No catalogs, adapters or design standards
are added by this block.

### A0.5 — Neutral Capacity Abstractions
- frozen supplied CapacityValue with explicit component, positive magnitude and unit
- free-form limit state, optional PropertySource and member/section/material references
- DemandCheck accepts CapacityValue instead of an unlabelled scalar
- exact component/unit/member compatibility; computed finite ratio and pass flag
- no resistance formulas, unit conversions or reference resolution

See `docs/STRUCTURAL_CORE_CAPACITY.md` for the API and migration example.

### A0.6 — Steel Flexural Yield Capacity
- first calculated capacity, in the separate design.steel layer
- explicit factor * Fy * Zx/Zy returning the existing Core CapacityValue
- caller declares component m2/m3 and section axis x/y independently
- exact MPa/mm inputs produce N*mm; unsupported pairs fail without conversion
- no complete design-standard module, compactness, LTB or buckling checks

See `docs/STEEL_FLEXURAL_YIELD_CAPACITY.md` for the API, limitations and neutral
DemandCheck integration.

### A0.7 — Steel Axial Yield Capacity
- second calculated capacity, in design.steel, returning Core CapacityValue
- explicit factor * Fy * supplied area; fixed component p and N output
- exact MPa/mm inputs only, without scale changes or unit conversion
- positive yield magnitude for either demand sign, not complete axial design
- no compression buckling, fracture, net-area or design-standard checks

See `docs/STEEL_AXIAL_YIELD_CAPACITY.md` for validation, provenance and integration
with the existing DemandCheck.

### A0.8 — Steel Euler Elastic Buckling Capacity
- ideal elastic Euler capacity in design.steel, returning Core CapacityValue
- explicit axis x/y, physical length, effective-length K and capacity factor
- slenderness K*L/r, Fe = pi^2*E/slenderness^2, Pcr = Fe*A
- exact MPa/mm inputs; L uses section length units; output N without conversion
- independent of axial yielding, with no Fy cap or automatic governing selection
- no complete AISC/E.090 compression design or inelastic compression curve

See `docs/STEEL_EULER_BUCKLING_CAPACITY.md` for assumptions and validation.

### A0.9 — Governing Capacity Selection
- neutral governing selection among already-calculated compatible capacities
- minimum positive magnitude; original CapacityValue returned with provenance intact
- exact component/unit/member/section/material compatibility, including absent references
- deterministic limit-state/source tie breaking; single-pass iterable validation
- caller controls candidates and applicability; no calculators or design-standard semantics

See `docs/GOVERNING_CAPACITY_SELECTION.md` for compatibility, duplicates and ties.

## Track B — SAP2000 Adapter (parallel)

### B1.1 — Read-only connection spike
- attach to a running SAP2000 instance
- report version/model name/path/units
- no writes

### B1.2 — Read model
- list frame objects
- frame section assignment
- endpoints and length

### B1.3 — Structural Core Geometry
- neutral Point3D, Node and StructuralModel
- unique identifiers and validated node/section references
- read-only geometry from frame endpoints, in explicit present length units

### B1.4 — SAP2000 Analysis Command
- run analysis as an explicit Command
- validate CSI return codes
- require an established connection; no retries or silent reconnection
- queries never trigger analysis; no results reading

### B1.5 — SAP2000 Frame Results Reader
- explicit query for one frame's P/V2/V3/T/M2/M3
- current output selection only; never analyze or select cases implicitly
- preserve object/element stations, case/combo, step and present units
- strict arrays validation and deterministic neutral output

### Future results (outside B1.5)
- displacements and other result capabilities, separately scoped

## Track C — Existing Tekla MCP (parallel)

Continue current capability expansion independently:
- read quantities
- create members
- components/connections
- reports/drawings

Constraint: avoid coupling Tekla code directly to SAP2000. Integration happens through
Structural Core contracts once stabilized.

## Next milestone

A reproducible vertical slice:

SAP2000 open model -> connect -> list frames/sections -> run analysis -> read
P/V2/V3/T/M2/M3 + displacement -> normalized JSON -> tests/validation record.
