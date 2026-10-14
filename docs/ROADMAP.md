# Roadmap

## Track A — Structural Core (parallel)

### A0.1 — Domain skeleton
- ModelInfo
- Member
- Section
- FrameForces
- AnalysisResult
- stable JSON serialization

### A0.2 — Units and envelopes
- explicit force/length unit metadata
- result envelope model
- member-end vs station results

### A0.3 — Checks engine
- deflection check
- generic utilization/check result

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
