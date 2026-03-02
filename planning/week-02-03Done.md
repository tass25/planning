# Week 2–3 Done: L2-B — StreamAgent, StateAgent & Documentation

> **Dates**: Feb 20–21, 2026
> **Layer**: L2-B (Streaming Core)
> **Branch**: `main`
> **Commits**: `dfd640a` → `46a4e50` → `020c3b7` → `617e9c3` → `7665486` → `b2b2dd4` → `aabf873` → `1e53f61` → `4112993` → `bb2e30f`

---

## 🎯 Objective

Implement the line-level streaming core of the partition pipeline: a `StreamAgent` that reads `.sas` files line by line, and a `StateAgent` that maintains a finite-state machine to track which block type is currently open. Together they form the real-time detection backbone used by all later parsing agents.

Also finalize all project documentation: UML diagrams, technology justification matrix, architecture HTML pages, and the cahier des charges update.

---

## ✅ What Was Done

### 1. StreamAgent (`1e53f61`)

Located at `partition/streaming/stream_agent.py`.

**What it does**:
- Reads a SAS file asynchronously line by line using `aiofiles`.
- Yields `(line_number: int, raw_line: str)` tuples.
- Skips empty lines and normalises line endings (`\r\n` → `\n`).
- Respects a configurable `max_lines` guard to prevent memory overrun on pathological files.

**Why async streaming**: A naive `readlines()` approach on a 250 KB SAS file would load the entire file into memory before any processing starts. The async generator approach enables the StateAgent to begin work immediately on line 1 while lines 2–N are still being read from disk.

---

### 2. StateAgent (`1e53f61`)

Located at `partition/streaming/state_agent.py`.

**What it does**:
- Consumes the `StreamAgent` generator.
- Maintains a `PartitionState` dataclass tracking the currently-open block type, its start line, and a `pending_block_start` pointer (the line number of the most recent standalone comment, used to "backtrack" block starts to include their header comments).
- Emits `RawBlockEvent(block_type, line_start, line_end, raw_code)` objects when a block closes.

**Regex-based detection**: Every line is matched against a priority-ordered set of compiled regexes:

| Priority | Regex Name | Matches |
|----------|-----------|---------|
| 1 | `MACRO_DEF` | `%MACRO name` |
| 2 | `MACRO_CALL` | `%name(...)` or `%name;` |
| 3 | `DATA` | `DATA name;` |
| 4 | `PROC` | `PROC name` |
| 5 | `RUN_QUIT` | `RUN;` / `QUIT;` (closes DATA/PROC) |
| 6 | `MEND` | `%MEND` (closes MACRO_DEF) |
| 7 | `IF_THEN` | `%IF … %THEN` |
| 8 | `DO_LOOP` | `%DO` / `DO` |
| 9 | `END` | `%END;` / `END;` |
| 10 | `GLOBAL` | `OPTIONS`, `LIBNAME`, `FILENAME`, `TITLE`, `%LET` |

**Implicit close logic**: When a new block opener is found while another block is already open, the `_IMPLICIT_CLOSE_SET` determines whether the old block auto-closes. For example, a `PROC` statement inside an open `DATA` step is treated as implicitly closing the `DATA` step (SAS does not require an explicit `RUN;`).

---

### 3. Pipeline Wiring

`partition/streaming/__init__.py` exposes a `run_pipeline(sas_path)` coroutine that wires `StreamAgent → StateAgent` and returns a list of `RawBlockEvent` objects. This is the entry point consumed by the chunking layer (L2-C) in the next week.

---

### 4. Unit Tests (7 tests) (`1e53f61`)

Tests in `tests/test_stream_state.py`:

| Test | What it checks |
|------|---------------|
| `test_data_step_detected` | `DATA x; SET y; RUN;` → one `DATA_STEP` event |
| `test_proc_block_detected` | `PROC MEANS; RUN;` → one `PROC_BLOCK` event |
| `test_macro_definition_detected` | `%MACRO m; … %MEND;` → one `MACRO_DEFINITION` event |
| `test_macro_invocation_detected` | `%my_macro;` → one `MACRO_INVOCATION` event |
| `test_implicit_close_data` | PROC inside open DATA → DATA closes, PROC opens |
| `test_global_statement` | `OPTIONS linesize=80;` → one `GLOBAL_STATEMENT` event |
| `test_pending_block_start` | Comment before DATA → block start backtracks to comment line |

All 7 pass.

---

### 5. Documentation Sprint (`dfd640a`, `46a4e50`, `aabf873`, `bb2e30f`)

This week also produced the bulk of project documentation:

#### docs/PROJECT.md
Full layer-by-layer description of all 16 planned agents, their inputs/outputs, and success gates.

#### docs/TECH_JUSTIFICATIONS.md
A technology justification matrix with 16 choices, each documented with:
- The decision (e.g., "LogReg + Platt calibration for ComplexityAgent")
- Alternatives considered (e.g., "XGBoost, Random Forest")
- Reason for choosing (ECE target < 0.08, small dataset, interpretability)
- 7 experiment protocols for future ablations

#### UML_DIAGRAMS.html (`dfd640a`, `bb2e30f`)
Five Mermaid-rendered diagrams:
1. **Class diagram** — all 16 agent classes, inheritance from `BaseAgent`
2. **Sequence diagram** — end-to-end file processing flow
3. **State machine diagram** — `StateAgent` FSM with all transitions
4. **Component diagram** — layer interactions (L2-A → L2-B → L2-C → L2-D)
5. **Frontend sequence diagram** — admin dashboard API flow

#### architecture_v2.html (`2eb9a8d`)
Interactive HTML with:
- 16 agents mapped to pipeline layers
- 721-block gold corpus stats
- Data lineage ER diagram
- DB schema (SQLite tables)
- Full tech stack (Python 3.10, Pydantic v2, SQLAlchemy, scikit-learn, Groq API)

#### Technology Justification Matrix additions (`aabf873`)
- Key choice: **structlog** over Python `logging` (structured JSON, context binding)
- Key choice: **Pydantic v2** over dataclasses (runtime validation, serialization)
- Key choice: **aiofiles** for async I/O (avoids blocking the event loop)

---

## ❌ Errors & Struggles

### Error 1: Mermaid v10.9.5 class diagram syntax failure (`020c3b7`)

**Problem**: The UML class diagram used arrow syntax `ClassA --> ClassB : "label"` which is valid in Mermaid v9 but causes a parse error in Mermaid v10.9.5 (which VS Code's preview renderer uses). The diagram rendered as a blank white box.

**Symptom**: Opening `UML_DIAGRAMS.html` in the editor showed no diagram, only the source code.

**Solution**: Rewrote class inheritance arrows using the Mermaid v10 syntax: `ClassA --|> ClassB`. Also moved method definitions inside class blocks to use `+method() ReturnType` notation. Took ~45 min to find the correct v10 syntax from the Mermaid changelog.

---

### Error 2: Agent count inconsistency across documents (`617e9c3`)

**Problem**: After adding `DataLineageExtractor` in week 1–2 (which brought the total to 16 agents), older documents (`README.md`, `architecture_v2.html`, `week-08.md`, `week-13.md`, `week-14.md`) still said "15 agents". Similarly, some documents still said "150 blocks" instead of "721".

**Symptom**: Inconsistent numbers when reviewing documentation for the report.

**Solution**: Ran a text search across all docs, found 12 occurrences of the old numbers, and replaced all in a single consistency pass commit (`617e9c3`).

---

### Error 3: `StateAgent` did not handle consecutive `%PUT` before `%MACRO` correctly

**Problem**: During manual testing, the pattern:
```sas
/* Phase 1 startup */
%PUT NOTE: === PHASE 1 ===;
%mymacro(arg1, arg2);
```
caused the `%PUT NOTE:` line to be detected as a `GLOBAL_STATEMENT`, which consumed the `pending_block_start` pointer. The macro call that followed then lost its header comment and got a start line one line too late.

**Symptom**: In manual inspection, the block for `%mymacro` started at the `%mymacro` line itself instead of the `/* Phase 1 startup */` comment line.

**Impact at this stage**: Not yet measurable (benchmark not built yet). Became a measured regression in week 4 (−17 blocks) and was fixed then.

**Why not fixed this week**: The benchmark did not yet exist, so the magnitude of the problem was invisible. Priority was getting to a working pipeline first.

---

### Error 4: async tests causing `DeprecationWarning` (carry-over from week 1)

**Problem**: The 7 streaming tests used `asyncio.get_event_loop().run_until_complete()`. When running all tests together (week 1 tests + week 2 tests), Python 3.10 printed 22 deprecation warnings (some for each test).

**Temporary solution applied**: Left the existing `test_boundary_detector.py` with the old pattern (refactoring it was deemed lower priority than building features). New test files added in week 4 use `asyncio.run()`.

---

### Struggle: Deciding where `pending_block_start` logic belongs

**Problem**: The "backtrack to include header comments" feature could live in `StreamAgent` (don't yield comment lines separately) or `StateAgent` (remember the last comment line). 

**Decision made**: Put it in `StateAgent` as a `pending_block_start: int | None` field because:
- `StreamAgent` should stay simple (just read lines)
- `StateAgent` already owns the FSM state — it's natural for it to own "what did the last comment say"

This decision proved correct but caused complexity later when `%PUT NOTE:` lines were being mistakenly treated as "header comments" rather than `GLOBAL_STATEMENT` markers.

---

## 📊 Outputs & Results

| Metric | Value |
|--------|-------|
| Agents implemented | 2 (StreamAgent, StateAgent) |
| Unit tests | 7 (all passing) |
| Total tests in suite | 22 (15 from week 1 + 7 new) |
| Documentation pages | 5 (PROJECT.md, TECH_JUSTIFICATIONS, UML, architecture_v2, globalARCH) |
| UML diagrams | 5 Mermaid diagrams |
| Tech choices documented | 16 |
| Benchmark score | N/A (benchmark not yet built) |
| Lines of production code added | ~320 (StreamAgent + StateAgent + pipeline wiring) |

---

## 💡 Key Learnings

- Building the FSM in `StateAgent` before having any benchmark was risky. Many edge cases (implicit closes, comment backsteps, PUT banners) only became visible when measured against gold data.
- Mermaid syntax is version-sensitive — always pin or test in the exact renderer being used.
- Writing 16-choice justifications early was valuable: when challenged in code review, the reasoning was already documented.
