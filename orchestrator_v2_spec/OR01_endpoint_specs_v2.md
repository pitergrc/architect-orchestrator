# OR01 — Endpoint Specs v2

## /parse
Returns:
- main_ask
- secondary_asks
- constraints
- deliverable_hint
- misread_risk

## /classify
Returns:
- primary_task_class
- secondary_task_class
- difficulty
- stakes
- route_confidence
- re_route_allowed

## /execution-plan
Returns:
- execution_mode
- tool_mandatory
- verifier_required
- critic_required
- carryover_required
- constraints_check_required
- deployability_check_required
- max_passes
- max_repair_cycles
- deliverable_contract

## /constraints-check
Returns:
- hard_constraints
- deployability_risk
- artifact_validation_required
- known_environment_limits

## /preflight
Returns compact packet for model runtime:
- ask_ledger
- task_profile
- execution_flags
- constraints_flags
- deliverable_contract
- risk_flags

## /postcheck
Returns:
- result
- issues
- lost_asks
- status_too_strong
- repair_needed
- recommended_status
