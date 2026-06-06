#!/bin/sh
set -e

# KB seeding disabled at startup — the Nomic model download (~280 MB)
# can exceed the health probe timeout.  Run manually if needed:
#   python /app/backend/scripts/kb/seed_kb.py --clear

exec python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
