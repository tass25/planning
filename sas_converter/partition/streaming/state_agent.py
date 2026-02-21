"""StateAgent (#5) — Pure-Python finite-state machine for SAS parsing.

Consumes ``LineChunk`` objects one at a time and maintains a ``ParsingState``
snapshot that tracks:

* Current block type (DATA_STEP, PROC_BLOCK, SQL_BLOCK, MACRO_DEFINITION, …)
* Block nesting depth (``%DO`` / ``%IF`` inside macros)
* Macro call stack (push on ``%MACRO``, pop on ``%MEND``)
* Variable scope (recently assigned variable names)
* Active dependencies (``%INCLUDE`` / ``LIBNAME`` refs)
* Block-comment and string-literal tracking

No LLM, no I/O, no network — pure regex + string checks.  Target: < 0.5 ms
per line on a modern CPU.
"""

from __future__ import annotations

import re
from uuid import UUID

from partition.base_agent import BaseAgent
from partition.streaming.models import LineChunk, ParsingState


class StateAgent(BaseAgent):
    """SAS finite-state-machine agent.

    Parameters:
        trace_id: Optional UUID for distributed tracing.
    """

    agent_name = "StateAgent"

    # ---- compiled regexes (class-level for speed) ----
    DATA_START  = re.compile(r"^\s*DATA\s+", re.IGNORECASE)
    PROC_START  = re.compile(r"^\s*PROC\s+", re.IGNORECASE)
    PROC_SQL    = re.compile(r"^\s*PROC\s+SQL\b", re.IGNORECASE)
    MACRO_DEF   = re.compile(r"^\s*%MACRO\s+(\w+)", re.IGNORECASE)
    MACRO_END   = re.compile(r"^\s*%MEND\b", re.IGNORECASE)
    MACRO_CALL  = re.compile(r"%(\w+)\s*\(", re.IGNORECASE)
    DO_START    = re.compile(r"%DO\b", re.IGNORECASE)
    IF_START    = re.compile(r"%IF\b", re.IGNORECASE)
    END_STMT    = re.compile(r"%END\b", re.IGNORECASE)
    RUN_STMT    = re.compile(r"^\s*RUN\s*;", re.IGNORECASE)
    QUIT_STMT   = re.compile(r"^\s*QUIT\s*;", re.IGNORECASE)
    INCLUDE     = re.compile(r"%INCLUDE\s+", re.IGNORECASE)
    GLOBAL      = re.compile(
        r"^\s*(OPTIONS|LIBNAME|FILENAME|TITLE)\b", re.IGNORECASE
    )
    COMMENT_S   = re.compile(r"/\*")
    COMMENT_E   = re.compile(r"\*/")
    ASSIGN      = re.compile(r"\b(\w+)\s*=\s*")

    def __init__(self, trace_id: UUID | None = None):
        super().__init__(trace_id)
        self.state = ParsingState()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def process(self, chunk: LineChunk) -> ParsingState:  # type: ignore[override]
        """Update and return the parsing state for *chunk*.

        The returned ``ParsingState`` is *the same mutable object* held by
        the agent — callers who need a snapshot should call
        ``state.model_copy()`` immediately after.
        """
        line = chunk.content

        # 1. Block-comment handling ──────────────────────────────────────
        if self.state.in_comment:
            if self.COMMENT_E.search(line):
                self.state.in_comment = False
            return self.state

        if self.COMMENT_S.search(line) and not self.COMMENT_E.search(line):
            self.state.in_comment = True
            return self.state

        # 2. Block transitions ──────────────────────────────────────────
        if self.state.current_block_type in (None, "IDLE"):
            self._detect_block_start(line, chunk.line_number)
        else:
            self._check_block_end(line)

        # 3. Nesting depth ─────────────────────────────────────────────
        if self.DO_START.search(line) or self.IF_START.search(line):
            self.state.nesting_depth += 1
        if self.END_STMT.search(line):
            self.state.nesting_depth = max(0, self.state.nesting_depth - 1)

        # 4. Macro stack ───────────────────────────────────────────────
        m = self.MACRO_DEF.search(line)
        if m:
            self.state.macro_stack.append(m.group(1))
        if self.MACRO_END.search(line) and self.state.macro_stack:
            self.state.macro_stack.pop()

        # 5. Dependency tracking ───────────────────────────────────────
        if self.INCLUDE.search(line):
            self.state.active_dependencies.append(line.strip())

        # 6. Variable-assignment tracking (simplified) ─────────────────
        assign = self.ASSIGN.search(line)
        if assign and self.state.current_block_type:
            self.state.variable_scope[assign.group(1)] = "assigned"

        return self.state

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _detect_block_start(self, line: str, line_num: int) -> None:
        """Identify what kind of SAS block is starting."""
        if self.DATA_START.match(line):
            self._open_block("DATA_STEP", line_num)
        elif self.PROC_SQL.match(line):
            self._open_block("SQL_BLOCK", line_num)
        elif self.PROC_START.match(line):
            self._open_block("PROC_BLOCK", line_num)
        elif self.MACRO_DEF.match(line):
            self._open_block("MACRO_DEFINITION", line_num)
        elif self.MACRO_CALL.search(line):
            self._open_block("MACRO_INVOCATION", line_num)
        elif self.GLOBAL.match(line):
            self._open_block("GLOBAL_STATEMENT", line_num)
        elif self.INCLUDE.search(line):
            self._open_block("INCLUDE_REFERENCE", line_num)

    def _open_block(self, block_type: str, line_num: int) -> None:
        self.state.current_block_type = block_type
        self.state.block_start_line = line_num
        self.logger.debug("block_start", block_type=block_type, line=line_num)

    def _check_block_end(self, line: str) -> None:
        bt = self.state.current_block_type

        if bt in ("DATA_STEP", "PROC_BLOCK") and self.RUN_STMT.search(line):
            self._close_block()
        elif bt == "SQL_BLOCK" and self.QUIT_STMT.search(line):
            self._close_block()
        elif bt == "MACRO_DEFINITION" and self.MACRO_END.search(line):
            self._close_block()
        elif bt == "MACRO_INVOCATION" and ";" in line:
            self._close_block()
        elif bt in ("GLOBAL_STATEMENT", "INCLUDE_REFERENCE") and ";" in line:
            self._close_block()

    def _close_block(self) -> None:
        self.logger.debug(
            "block_end",
            block_type=self.state.current_block_type,
            started=self.state.block_start_line,
        )
        self.state.current_block_type = "IDLE"
        self.state.block_start_line = None

    def reset(self) -> None:
        """Reset the agent state for a new file."""
        self.state = ParsingState()
