# backend/api/services — Service Layer

## Purpose
Business logic extracted from route handlers. Routes are kept thin (HTTP concerns only);
heavy lifting lives here.

## Modules

| File | Responsibility |
|------|----------------|
| `conversion_service.py` | `conv_to_out()` ORM→schema mapping; `STAGES` / `STAGE_DISPLAY_MAP` constants |
| `pipeline_service.py`   | `run_pipeline_sync()` — 8-stage background pipeline (L2-A agents + LLM translation) |
| `translation_service.py` | `translate_sas_to_python()` — Azure OpenAI → Groq fallback chain; `_SAS_CONVERSION_RULES` system prompt |

## Usage

```python
from api.services.conversion_service import conv_to_out, STAGES
from api.services.pipeline_service import run_pipeline_sync
from api.services.translation_service import translate_sas_to_python
```

Or via the package `__init__`:
```python
from api.services import conv_to_out, run_pipeline_sync, translate_sas_to_python
```

## Dependencies
- `config.settings` — for LLM provider credentials
- `config.constants` — for token limits and timeouts
- `api.core.database` — for ORM models (pipeline_service)
- `partition.*` — lazy-imported inside functions to avoid circular imports
