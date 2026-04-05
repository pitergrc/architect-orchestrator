# OR03 — Payload Examples v2

## Example classify request
```json
{
  "text": "Найди баг, предложи patch и проверь, не сломает ли это существующий код",
  "parsed": {
    "main_ask": "Найти баг и предложить patch",
    "secondary_asks": ["Проверить риск регрессии"],
    "constraints": [],
    "deliverable_hint": "patch",
    "misread_risk": "low"
  }
}
```

## Example classify response
```json
{
  "primary_task_class": "coding",
  "secondary_task_class": "diagnosis",
  "difficulty": "high",
  "stakes": "medium",
  "route_confidence": "high",
  "re_route_allowed": true
}
```

## Example execution-plan response
```json
{
  "execution_mode": "deep",
  "tool_mandatory": false,
  "verifier_required": true,
  "critic_required": false,
  "carryover_required": false,
  "constraints_check_required": true,
  "deployability_check_required": false,
  "max_passes": 2,
  "max_repair_cycles": 1,
  "deliverable_contract": "patch"
}
```

## Example postcheck response
```json
{
  "result": "repairable_defect",
  "issues": ["missing regression risk", "status too strong"],
  "lost_asks": [],
  "status_too_strong": true,
  "repair_needed": true,
  "recommended_status": "provisional"
}
```
