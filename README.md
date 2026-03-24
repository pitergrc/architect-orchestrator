# Architect Orchestrator

Render-only lite orchestration service for Architect GPT.

## Production mode
Primary mode:
- Auto-Orchestrator Lite = ON
- Heavy Orchestration = trigger-based
- runOrchestrator = hidden fallback

## Public production endpoints
- GET /health
- GET /healthz
- POST /parse
- POST /route
- POST /preflight
- POST /postcheck

## Hidden fallback endpoint
- POST /orchestrate

`/orchestrate` stays in the codebase as a legacy/dev/fallback path.
By default:
- RUN_ORCHESTRATOR_ENABLED=false
- RUN_ORCHESTRATOR_PUBLIC=false

That means:
- GPT Actions do not see `/orchestrate`
- calling `/orchestrate` directly returns a controlled 503 unless explicitly enabled

## Environment variables
Required for Render production:
- RUNTIME_MODE=FULL_CORE
- LOG_PATH=logs/events.jsonl
- PUBLIC_BASE_URL=https://YOUR-SERVICE.onrender.com
- AUTO_ORCHESTRATOR_LITE=ON
- HEAVY_ORCHESTRATION_TRIGGER=ON
- RUN_ORCHESTRATOR_ENABLED=false
- RUN_ORCHESTRATOR_PUBLIC=false

Legacy/dev only:
- OLLAMA_BASE_URL=http://127.0.0.1:11434
- OLLAMA_MODEL=gemma3:1b

## Render deploy
Build Command:
`pip install -r requirements.txt`

Start Command:
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`

## Notes
- Production path is Render-only and does not rely on local PC or local Ollama.
- Do not use free Render Key Value or free Render Postgres as the source of truth for long-term critical state.
- Use Render Environment Variables or Environment Groups for secrets.
