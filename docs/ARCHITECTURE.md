# Architecture decisions

## AD-001 — One platform, multiple adapters

The project is not a collection of unrelated MCP servers. The reusable product is the
Structural Core plus workflow/application services. MCP is one transport layer.

## AD-002 — Keep Tekla work independent for now

The existing Tekla MCP can continue in parallel. Do not merge repositories yet.
When core contracts stabilize, add a Tekla adapter that maps current Tekla operations
to the shared models.

## AD-003 — Queries vs Commands

Queries do not mutate external models. Commands may mutate or execute analysis.
This distinction will later support approvals, audit logs and agent safety.

## AD-004 — Proprietary APIs stay behind adapters

COM/OAPI/REST/SDK response shapes must never leak into the Structural Core.
Normalize return codes, arrays, units and identifiers inside each adapter.

## AD-005 — Workflow engine before visual editor

A workflow is executable JSON/data first. A node editor is a later presentation layer.
The same workflow should eventually run from UI, CLI, MCP or API.
