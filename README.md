# JYM Structural Automation

Platform for structural-engineering automation across analysis, connection design, BIM and reporting.

## Initial scope

Phase 0-1 focuses on a neutral Structural Core and a read-only SAP2000 adapter:

1. Connect to an open SAP2000 model.
2. Read model metadata, frame objects and sections.
3. Run analysis through an explicit command boundary.
4. Read frame forces and displacements.
5. Normalize results into application-owned models/JSON.
6. Keep all software-specific API details inside adapters.

## Architecture

```text
UI / MCP / CLI
      |
Workflow Engine
      |
Structural Core
      |
+-----+--------+----------+---------+
|              |          |         |
SAP2000      IDEA       Tekla     Revit / GH
Adapter      Adapter     Adapter    Adapter
```

## Repository principles

- The Structural Core must not depend on SAP2000, Tekla, IDEA StatiCa, Revit or Grasshopper SDKs.
- Adapters translate proprietary APIs into core models.
- Queries and Commands are separated.
- Read operations are implemented before write operations.
- Every validated external-API operation gets a test or reproducible validation record.
- AI/MCP tools call stable application services; they do not execute arbitrary generated code as the normal path.

## Parallel development

Current recommended workstreams:

- `feature/structural-core`
- `feature/sap2000-adapter`
- Existing Tekla MCP remains in its current repository until adapter contracts stabilize.

See `docs/ROADMAP.md` and `docs/ARCHITECTURE.md`.
