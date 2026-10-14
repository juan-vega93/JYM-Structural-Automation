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

### B1.3 — Analysis boundary
- run analysis as an explicit Command
- validate CSI return codes
- reconnect/health-check policy

### B1.4 — Results
- frame forces P/V2/V3/T/M2/M3
- displacements
- load case/combo + station
- normalization into core models

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
