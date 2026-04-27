# Week 2–3 Visualization: Streaming Core

> Artifacts produced: None (this week built the streaming pipeline foundation, no persistent DB artifacts)

**What this week delivered:**
- `StreamAgent` — async line-by-line reader
- `StateAgent` — FSM for block detection
- Backpressure queue

**Why no visualization artifacts:**
The streaming core produces ephemeral `RawBlockEvent` objects in memory that are immediately consumed by downstream agents (BoundaryDetectorAgent in Week 3–4). No persistent database or graph is written at this stage.

**To see these agents in action:**
Run the full pipeline on `main` and watch the logs — you'll see `stream_agent_read_line` and `state_agent_block_detected` events in the console output.
