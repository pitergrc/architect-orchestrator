# OR04 — Rollout Checklist v2

## Before code changes
- backup current instruction
- backup current action schema
- backup current endpoint behavior
- note Render base URL and env var names

## Backend changes
- add /classify
- add /execution-plan
- add /constraints-check
- keep /route temporarily
- extend /parse, /preflight, /postcheck

## Schema changes
- add new paths
- add new request/response schemas
- keep backward compatibility where possible
- validate OpenAPI before pasting into GPT

## Deploy checks
- deploy to Render
- inspect Events
- inspect Logs
- confirm no 422 or 500 on new endpoints

## GPT checks
- update Action schema
- test in Preview
- test formal / coding / research / planning / constraint task
- only after success, downgrade /route
