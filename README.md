# Architect Orchestrator v1

Локальный бесплатный оркестратор для AnalyzerCore:
- FastAPI API
- LangGraph workflow
- Ollama backend
- JSONL telemetry
- Простейшие preflight/postcheck проверки

## Структура
- `app/main.py` — FastAPI entrypoint
- `app/schemas.py` — Pydantic модели
- `app/parser.py` — prompt parse
- `app/router.py` — route resolver
- `app/runtime.py` — preflight/activation
- `app/postcheck.py` — post-check и flags
- `app/telemetry.py` — JSONL логирование
- `app/graph.py` — LangGraph workflow
- `app/llm.py` — вызов Ollama API
- `logs/events.jsonl` — события telemetry

## Быстрый старт
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
fastapi dev app\main.py
```

После старта:
- docs: `http://127.0.0.1:8000/docs`
- openapi: `http://127.0.0.1:8000/openapi.json`
- health: `http://127.0.0.1:8000/health`

## Ollama
По умолчанию оркестратор ходит в:
- `http://127.0.0.1:11434/api/chat`

Модель по умолчанию:
- `gemma3`

Поменять можно через `.env`.

## Эндпоинты
- `GET /health`
- `POST /parse`
- `POST /route`
- `POST /preflight`
- `POST /postcheck`
- `POST /orchestrate`

## Cloudflare Tunnel
Когда локальный сервер готов, можно открыть наружу:
```powershell
cloudflared tunnel --url http://localhost:8000
```

## Замечания
Это стартовый рабочий каркас.
Он не заменяет AnalyzerCore и не дублирует law; он только делает runtime-enforcement.
