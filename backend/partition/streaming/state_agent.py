"""StateAgent (#5)  Pure-Python finite-state machine for SAS parsing.

Consumes ``LineChunk`` objects one at a time and maintains a ``ParsingState``
snapshot that tracks:

* Current block type (DATA_STEP, PROC_BLOCK, SQL_BLOCK, MACRO_DEFINITION, )
* Block nesting depth (``%DO`` / ``%IF`` inside macros)
* Macro call stack (push on ``%MACRO``, pop on ``%MEND``)
* Variable scope (recently assigned variable names)
* Active dependencies (``%INCLUDE`` / ``LIBNAME`` refs)
* Block-comment and string-literal tracking
* last_closed_block  records a block that opened AND closed in one chunk

No LLM, no I/O, no network  pure regex + string checks.
"""

from __future__ import annotations

import re
from uuid import UUID

from partition.base_agent import BaseAgent
from partition.streaming.models import LineChunk, ParsingState

# Block types that end via an explicit keyword (RUN/QUIT/%MEND/%END).
_EXPLICIT_CLOSE = {"DATA_STEP", "PROC_BLOCK", "SQL_BLOCK", "MACRO_DEFINITION",
                   "CONDITIONAL_BLOCK", "LOOP_BLOCK"}

# Only these can be implicitly closed when a new top-level keyword arrives.
# MACRO_DEFINITION, CONDITIONAL_BLOCK, LOOP_BLOCK are never implicitly closed —
# they require their explicit terminator (%MEND / %END;).
_IMPLICIT_CLOSEABLE = {"DATA_STEP", "PROC_BLOCK", "SQL_BLOCK"}

# Top-level keywords that implicitly close any open implicit-closeable block.
# GLOBAL_STATEMENT excluded so that %LET/%OPTIONS inside macros/DATA steps
# do not prematurely close those blocks.
_IMPLICIT_CLOSE_TRIGGERS = {
    "DATA_STEP", "PROC_BLOCK", "SQL_BLOCK", "MACRO_DEFINITION",
    "INCLUDE_REFERENCE",
}


class StateAgent(BaseAgent):
    """SAS finite-state-machine agent."""

    agent_name = "StateAgent"

    DATA_START  = re.compile(r"^\s*DATA\s+", re.IGNORECASE)
    PROC_START  = re.compile(r"^\s*PROC\s+", re.IGNORECASE)
    PROC_SQL    = re.compile(r"^\s*PROC\s+SQL\b", re.IGNORECASE)
    MACRO_DEF   = re.compile(r"^\s*%MACRO\s+(\w+)", re.IGNORECASE)
    MACRO_END   = re.compile(r"^\s*%MEND\b", re.IGNORECASE)
    MACRO_CALL  = re.compile(
        r"%(?!MACRO\b|MEND\b|DO\b|END\b|IF\b|ELSE\b|LET\b|PUT\b|INCLUDE\b|GLOBAL\b|LOCAL\b)(\w+)\s*[\(;]",
        re.IGNORECASE,
    )
    DO_START    = re.compile(r"%DO\b", re.IGNORECASE)
    IF_START    = re.compile(r"%IF\b", re.IGNORECASE)
    END_STMT    = re.compile(r"%END\b", re.IGNORECASE)
    RUN_STMT    = re.compile(r"^\s*RUN\s*;", re.IGNORECASE)
    QUIT_STMT   = re.compile(r"^\s*QUIT\s*;", re.IGNORECASE)
    INCLUDE     = re.compile(r"%INCLUDE\s+", re.IGNORECASE)
    GLOBAL      = re.compile(
        r"^\s*(?:"
        r"OPTIONS|LIBNAME|FILENAME|TITLE\d*|FOOTNOTE\d*"
        r"|%LET\b|%GLOBAL\b|%LOCAL\b"
        r"|DM\b|ODS\b"
        r"|RSUBMIT\b|ENDRSUBMIT\b"
        r"|%PUT\b"
        r")",
        re.IGNORECASE,
    )
    # Core GLOBAL triggers (OPTIONS/LIBNAME/etc.) — excludes %PUT NOTE/WARNING
    # Used to distinguish "real" GLOBAL_STATEMENTs from PUT-banner lines.
    GLOBAL_CORE = re.compile(
        r"^\s*(?:"
        r"OPTIONS|LIBNAME|FILENAME|TITLE\d*|FOOTNOTE\d*"
        r"|%LET\b|%GLOBAL\b|%LOCAL\b"
        r"|DM\b|ODS\b"
        r"|RSUBMIT\b|ENDRSUBMIT\b"
        r")",
        re.IGNORECASE,
    )
    # %PUT NOTE/WARNING/ERROR: banner lines — trigger GLOBAL but are dropped post-merge
    # unless merged with a GLOBAL_CORE event.
    PUT_LOG     = re.compile(r"^\s*%PUT\s+(?:NOTE|WARNING|ERROR)\s*:", re.IGNORECASE)
    COMMENT_S   = re.compile(r"/\*")
    COMMENT_E   = re.compile(r"\*/")
    # Strip from beginning of string through (and including) the first */
    # Used when in_comment=True to remove the comment-end prefix so that
    # code following the */ on the same chunk can still be processed.
    STRIP_TILL_COMMENT_E = re.compile(r"^.*?\*/", re.DOTALL)
    STRIP_COMMENT      = re.compile(r"/\*.*?\*/", re.DOTALL)
    STRIP_STAR_COMMENT = re.compile(r"^\s*\*[^;]*;", re.MULTILINE)
    ASSIGN      = re.compile(r"\b(\w+)\s*=\s*")
    # Macro flow-control blocks
    DO_STMT     = re.compile(r"^\s*%DO\b", re.IGNORECASE)   # loop start
    COND_IF     = re.compile(r"^\s*%IF\b", re.IGNORECASE)   # conditional start
    END_BLOCK   = re.compile(r"%END\s*;", re.IGNORECASE)     # LOOP/COND close
    # %ELSE, %ELSE %IF, %ELSE %DO — all continue a CONDITIONAL_BLOCK chain
    ELSE_CLAUSE = re.compile(r"^\s*%ELSE\b", re.IGNORECASE)

    def __init__(self, trace_id: UUID | None = None):
        super().__init__(trace_id)
        self.state = ParsingState()

    async def process(self, chunk: LineChunk) -> ParsingState:  # type: ignore[override]
        """Update and return the parsing state for *chunk*."""
        line = chunk.content
        line_num = chunk.line_number

        # Reset transient signal from previous chunk
        self.state.last_closed_block = None

        # First physical line of this chunk (before in_comment returns).
        # Used for pending_block_start backtracking throughout this method.
        chunk_start_early = max(1, line_num - line.count("\n"))

        # 1. Block-comment handling
        if self.state.in_comment:
            if self.COMMENT_E.search(line):
                self.state.in_comment = False
                # Strip everything from beginning through the closing */
                # so that code AFTER the comment on the same chunk is processed.
                # e.g. "-------- */\n    DATA work;" → "\n    DATA work;"
                line = self.STRIP_TILL_COMMENT_E.sub("", line, count=1)
                # If the line now has non-trivial content, fall through to process it.
                if not line.strip():
                    if self.state.current_block_type in (None, "IDLE") and self.state.pending_block_start is None:
                        self.state.pending_block_start = chunk_start_early
                    return self.state
                # Fall through to process the remaining content after the comment end
            else:
                # Still inside comment, nothing to process
                if self.state.current_block_type in (None, "IDLE") and self.state.pending_block_start is None:
                    self.state.pending_block_start = chunk_start_early
                return self.state

        if self.COMMENT_S.search(line) and not self.COMMENT_E.search(line):
            # Multi-line comment start: track for pending_block_start
            if self.state.current_block_type in (None, "IDLE") and self.state.pending_block_start is None:
                self.state.pending_block_start = chunk_start_early
            self.state.in_comment = True
            return self.state

        # 2. Clean line for pattern matching
        clean = self.STRIP_COMMENT.sub(" ", line)
        clean = self.STRIP_STAR_COMMENT.sub(" ", clean).strip()

        # First physical line of this (possibly multi-statement) chunk.
        # Used to backtrack block starts/ends to include leading comments.
        chunk_start = chunk_start_early

        # Track the last physical line containing real SAS code inside a block.
        # This is used when an implicit close happens after a multi-line comment:
        # the old block should end at the last real-code line, not inside the comment.
        # Do NOT update on lines that are themselves top-level block openers, because
        # those lines belong to the NEW block (they trigger implicit close of the old one).
        _is_block_opener = bool(
            self.DATA_START.match(clean)
            or self.PROC_START.match(clean)
            or self.PROC_SQL.match(clean)
            or self.MACRO_DEF.match(clean)
            or self.INCLUDE.search(clean)
            or self.DO_STMT.match(clean)
            or self.COND_IF.match(clean)
            or self.ELSE_CLAUSE.match(clean)
        )
        if clean.strip() and not _is_block_opener and self.state.current_block_type not in (None, "IDLE"):
            self.state.last_content_line = line_num

        # 3. Block transitions
        current_bt = self.state.current_block_type

        if current_bt in (None, "IDLE"):
            # Determine the chunk's first line — captures leading comments that
            # were coalesced with the keyword into the same chunk.
            # Update pending_block_start:
            #   • blank / comment-only clean  → mark this chunk start
            #   • chunk whose raw content starts with "/*" or "*" → also update
            #   • other non-block lines         → reset (e.g. %let statements)
            leads_with_comment = (
                not clean.strip()
                or line.lstrip().startswith("/*")
                or line.lstrip().startswith("*")
            )
            if leads_with_comment:
                if self.state.pending_block_start is None:
                    self.state.pending_block_start = chunk_start
                else:
                    self.state.pending_block_start = min(self.state.pending_block_start, chunk_start)
            else:
                # Non-comment line — preserve pending_block_start only if this
                # line is itself a block-opening trigger (so that the preceding
                # comment gets included in the block via _open_block backtrack).
                # Reset otherwise (stray %LET in IDLE, orphan semicolons, etc.)
                is_block_trigger = bool(
                    self.GLOBAL.match(clean)
                    or self.DATA_START.match(clean)
                    or self.PROC_START.match(clean)
                    or self.MACRO_DEF.match(clean)
                    or self.INCLUDE.search(clean)
                    or self.DO_STMT.match(clean)
                    or self.COND_IF.match(clean)
                    or self.ELSE_CLAUSE.match(clean)
                    or self.MACRO_CALL.search(clean)
                )
                if not is_block_trigger:
                    self.state.pending_block_start = None
                elif self.state.pending_block_start is None and chunk_start < line_num:
                    # Multi-line chunk (e.g. a macro call spanning several lines)
                    # with no preceding comment to anchor the start.
                    # Use the chunk's first physical line so the full call is included.
                    self.state.pending_block_start = chunk_start

            self._detect_and_open(clean, line_num)
            # Single-line block: check close in same chunk
            if self.state.current_block_type not in (None, "IDLE"):
                self._check_close(clean, line_num)
        else:
            # Implicit closure: new top-level keyword ends an open DATA/PROC/SQL block
            # when no RUN;/QUIT; came (e.g. consecutive DATA steps).
            # CONDITIONAL_BLOCK, LOOP_BLOCK are never implicitly closed —
            # they contain inner DATA/PROC/SQL and close only on their %END;.
            # MACRO_DEFINITION stays in _EXPLICIT_CLOSE so it IS implicitly closed
            # by new top-level blocks (preserving gsh_01-style whole-body macros).
            _IMPLICIT_CLOSE_SET = _EXPLICIT_CLOSE - {"CONDITIONAL_BLOCK", "LOOP_BLOCK"}
            new_type = self._peek_block_type(clean)
            if (
                new_type is not None
                and current_bt in _IMPLICIT_CLOSE_SET
                and new_type in _IMPLICIT_CLOSE_TRIGGERS
                and new_type != current_bt
            ):
                # Close the current block.  Use last_content_line (the last
                # non-comment code line) if available and closer than
                # chunk_start-1 — this handles the case where a multi-line
                # comment between two blocks makes chunk_start-1 land inside
                # the comment rather than on the actual last code line.
                raw_close = max(chunk_start - 1, self.state.block_start_line or line_num)
                if (
                    self.state.last_content_line is not None
                    and self.state.last_content_line < chunk_start
                ):
                    close_at = self.state.last_content_line
                else:
                    close_at = raw_close
                self.state.last_content_line = None  # reset for new block
                self._close_block(close_at)
                # The new block's start should include the leading comment.
                # If pending_block_start was already set (e.g. we saw COMMENT_S
                # for the incoming block's doc-comment earlier), prefer the
                # earlier value; otherwise fall back to chunk_start.
                if self.state.pending_block_start is None:
                    self.state.pending_block_start = chunk_start
                self._detect_and_open(clean, line_num)
                if self.state.current_block_type not in (None, "IDLE"):
                    self._check_close(clean, line_num)
            else:
                self._check_close(clean, line_num)

        # 4. Nesting depth
        if self.DO_START.search(line) or self.IF_START.search(line):
            self.state.nesting_depth += 1
        if self.END_STMT.search(line):
            self.state.nesting_depth = max(0, self.state.nesting_depth - 1)

        # 5. Macro stack
        m = self.MACRO_DEF.search(line)
        if m:
            self.state.macro_stack.append(m.group(1))
        if self.MACRO_END.search(line) and self.state.macro_stack:
            self.state.macro_stack.pop()

        # 6. Dependency tracking
        if self.INCLUDE.search(line):
            self.state.active_dependencies.append(line.strip())

        # 7. Variable-assignment tracking (simplified)
        assign = self.ASSIGN.search(line)
        if assign and self.state.current_block_type not in (None, "IDLE"):
            self.state.variable_scope[assign.group(1)] = "assigned"

        return self.state

    # ------------------------------------------------------------------
    def _peek_block_type(self, clean: str) -> str | None:
        """Return what block type *clean* would open, without changing state."""
        for part in (p.strip() for p in clean.split(";") if p.strip()):
            if self.DATA_START.match(part):    return "DATA_STEP"
            if self.PROC_SQL.match(part):      return "SQL_BLOCK"
            if self.PROC_START.match(part):    return "PROC_BLOCK"
            if self.MACRO_DEF.match(part):     return "MACRO_DEFINITION"
            if self.INCLUDE.search(part):      return "INCLUDE_REFERENCE"
            if self.GLOBAL.match(part):        return "GLOBAL_STATEMENT"
            if self.ELSE_CLAUSE.match(part):   return "CONDITIONAL_BLOCK"
            if self.DO_STMT.match(part):       return "LOOP_BLOCK"
            if self.COND_IF.match(part):       return "CONDITIONAL_BLOCK"
            if self.MACRO_CALL.search(part + ";"):   return "MACRO_INVOCATION"
        return None

    def _detect_and_open(self, clean: str, line_num: int) -> None:
        """Scan sub-statements for a block-opening keyword."""
        for part in (p.strip() for p in clean.split(";") if p.strip()):
            if self.DATA_START.match(part):
                self._open_block("DATA_STEP", line_num); return
            elif self.PROC_SQL.match(part):
                self._open_block("SQL_BLOCK", line_num); return
            elif self.PROC_START.match(part):
                self._open_block("PROC_BLOCK", line_num); return
            elif self.MACRO_DEF.match(part):
                self._open_block("MACRO_DEFINITION", line_num); return
            elif self.INCLUDE.search(part):
                self._open_block("INCLUDE_REFERENCE", line_num); return
            elif self.GLOBAL.match(part):
                # For %PUT NOTE/WARNING/ERROR: banner lines, open the GLOBAL block
                # so the event is emitted (enabling merge with adjacent OPTIONS/etc.),
                # but restore pending_block_start afterwards so the following
                # macro/proc call can still inherit the section comment header.
                # _merge_global_statements will drop the event if it remains
                # PUT-only (i.e. was never merged with a core GLOBAL trigger).
                if self.PUT_LOG.match(part):
                    saved_pending = self.state.pending_block_start
                    self._open_block("GLOBAL_STATEMENT", line_num)
                    # Restore pending so that the next block (e.g. %macro_call)
                    # can backtrack to the section comment.
                    if saved_pending is not None:
                        self.state.pending_block_start = saved_pending
                else:
                    self._open_block("GLOBAL_STATEMENT", line_num)
                return
            elif self.ELSE_CLAUSE.match(part):    # %ELSE / %ELSE %IF / %ELSE %DO
                # %ELSE %DO has an explicit %DO — needs %END; to close
                has_do = bool(self.DO_START.search(part))
                self._open_block("CONDITIONAL_BLOCK", line_num)
                self.state.cond_has_do = has_do
                return
            elif self.DO_STMT.match(part):        # %DO loop (before MACRO_CALL)
                self._open_block("LOOP_BLOCK", line_num)
                self.state.cond_has_do = True  # %DO always needs %END;
                return
            elif self.COND_IF.match(part):         # %IF conditional (before MACRO_CALL)
                # Check if this line contains %DO (single chunk %IF...%THEN %DO)
                has_do = bool(self.DO_START.search(part))
                self._open_block("CONDITIONAL_BLOCK", line_num)
                self.state.cond_has_do = has_do
                return
            elif self.MACRO_CALL.search(part + ";"):
                self._open_block("MACRO_INVOCATION", line_num); return

    def _open_block(self, block_type: str, line_num: int) -> None:
        # Use pending_block_start if within tolerance (leading section comments).
        # GLOBAL_STATEMENT allows a larger header-comment backtrack (up to 60 lines)
        # because SAS program headers can be long multi-line comment blocks.
        backtrack_limit = 60 if block_type == "GLOBAL_STATEMENT" else 15
        start = line_num
        if (
            self.state.pending_block_start is not None
            and (line_num - self.state.pending_block_start) <= backtrack_limit
        ):
            start = self.state.pending_block_start
        self.state.pending_block_start = None  # Consume the pending start
        self.state.current_block_type = block_type
        self.state.block_start_line = start
        self.state.cond_has_do = False  # Reset; set True by caller if %DO present
        self.state.last_content_line = None  # reset for new block
        self.logger.debug("block_start", block_type=block_type, line=start)

    def _check_close(self, clean: str, line_num: int) -> None:
        """Check whether the current block closes on *clean*."""
        bt = self.state.current_block_type
        if bt == "DATA_STEP" and self.RUN_STMT.search(clean):
            self._close_block(line_num)
        elif bt == "PROC_BLOCK" and (self.RUN_STMT.search(clean) or self.QUIT_STMT.search(clean)):
            self._close_block(line_num)
        elif bt == "SQL_BLOCK" and self.QUIT_STMT.search(clean):
            self._close_block(line_num)
        elif bt == "MACRO_DEFINITION" and self.MACRO_END.search(clean):
            self._close_block(line_num)
        elif bt in ("CONDITIONAL_BLOCK", "LOOP_BLOCK") and self.END_BLOCK.search(clean):
            self._close_block(line_num)
        elif bt == "CONDITIONAL_BLOCK" and not self.state.cond_has_do:
            # Single-line conditional: %IF...%THEN stmt; or %ELSE stmt; (no %DO/%END)
            # If the current chunk has %DO, upgrade to do-block (needs %END)
            if self.DO_START.search(clean):
                self.state.cond_has_do = True
            elif ";" in clean and not self.COND_IF.match(clean) and not self.ELSE_CLAUSE.match(clean):
                # Closing when we see any statement ending with ; that is not
                # itself a new %IF or %ELSE (which would extend the chain)
                self._close_block(line_num)
        elif bt == "MACRO_INVOCATION" and ";" in clean:
            self._close_block(line_num)
        elif bt in ("GLOBAL_STATEMENT", "INCLUDE_REFERENCE") and ";" in clean:
            self._close_block(line_num)

    def _close_block(self, end_line: int) -> None:
        bt    = self.state.current_block_type
        start = self.state.block_start_line or end_line
        self.logger.debug("block_end", block_type=bt, started=start)
        self.state.last_closed_block = (bt, start, end_line)
        self.state.current_block_type = "IDLE"
        self.state.block_start_line = None
        self.state.last_content_line = None

    def reset(self) -> None:
        """Reset the agent state for a new file."""
        self.state = ParsingState()
