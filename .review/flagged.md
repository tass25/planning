# Flagged Issues — Wave 1

Items found during Wave 1 that are outside scope or deferred.

## DEFERRED (by user instruction)
- CRITICAL #3: Best-of-N Translator — research contribution, explicitly skipped
- CRITICAL #3: Oracle Verification Agent — research contribution, explicitly skipped
- CRITICAL #3: Adversarial Pipeline — research contribution, explicitly skipped

## ALREADY FIXED (pre-existing, confirmed during audit)
- HIGH #4: Z3 Agent wiring — already wired in `translation_pipeline.py` lines 112–175
- UPLOAD_DIR path — already uses `Path(__file__).resolve()` pattern in pipeline_service.py
- Services layer — already exists at backend/api/services/
- Zustand store coupling — stores do NOT import from each other (confirmed)
- RAGRouter KBQueryClient sharing — KBQueryClient is stateless per call, safe to share (confirmed)

## KNOWN ISSUES TO WATCH
- `conv.accuracy = 100.0` in pipeline_service.py line 224 — hardcoded, TODO comment present
- CORS still hardcoded to localhost origins — needs prod domain when deploying
- GitHub OAuth callback is a stub (noted in CLAUDE.md, not a new finding)
- SQLite WAL + concurrent writes — acknowledged fragile area per CLAUDE.md
