# OR00 — Orchestrator Rebuild Plan v2

## Goal
Upgrade the current action-orchestrator from a parse/route/audit helper into an execution + constraints controller for universal hard tasks.

## Keep
- /health
- /healthz
- /parse
- /preflight
- /postcheck

## Deprecate later
- /route

## Add
- /classify
- /execution-plan
- /constraints-check

## Migration rule
Do not remove /route until the new pipeline works in:
- local tests
- Render logs
- GPT Preview

## Target pipeline
parse → classify → execution-plan → constraints-check → preflight → answer → postcheck
