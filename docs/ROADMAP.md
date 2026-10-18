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
