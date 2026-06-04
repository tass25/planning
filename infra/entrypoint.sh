#!/bin/sh
set -e

# Seed KB on first boot (skips if table already has data)
if [ ! -f /app/backend/data/.kb_seeded ]; then
    echo "[Codara] First boot — seeding Knowledge Base with 35 verified pairs..."
    python /app/backend/scripts/kb/seed_kb.py --clear 2>&1 || echo "[Codara] KB seed skipped (non-fatal)"
    touch /app/backend/data/.kb_seeded
fi

exec python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
