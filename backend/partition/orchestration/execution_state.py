"""execution_state.py — Materialized DataFrame state tracker between pipeline stages.

Tracks the actual DataFrames produced by each successfully translated+validated
chunk, propagating them forward so downstream chunks receive real column names,
row counts, and dtypes — not auto-generated placeholders.

Two trust levels:
  "materialized" : a real DataFrame was committed after a successful exec.
  "inferred"     : only schema was inferred from SAS code (no real data yet).

Usage::

    tracker = ExecutionStateTracker()

    # After TranslationPipeline succeeds for a partition:
    tracker.commit(
        table_name="customers",
        frame=actual_df,          # the real output DataFrame
        produced_by=partition.block_id,
    )

    # Before translating next partition — inject context into prompt metadata:
    context = tracker.get_context_for_partition(partition)
    partition.metadata["upstream_state"] = context

    # Direct lookup:
    state = tracker.get_artifact("customers")
    if state and state.trust_level == "materialized":
        print(state.frame.shape)
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
import structlog

logger = structlog.get_logger()

_MAX_COLS_IN_CONTEXT = 20   # avoid bloating the prompt
_MAX_ROWS_SHOWN      = 3    # sample rows shown in context


# ── data models ───────────────────────────────────────────────────────────────

@dataclass
class TableState:
    table_name:   str
    trust_level:  str                          # "materialized" | "inferred"
    cols:         list[str]  = field(default_factory=list)
    nb_rows:      int        = 0
    sorted_by:    list[str]  = field(default_factory=list)
    dtypes:       dict[str, str] = field(default_factory=dict)
    frame:        Optional[pd.DataFrame] = field(default=None, repr=False)
    produced_by:  Optional[uuid.UUID] = None   # block_id that created this table

    def describe(self) -> str:
        trust_tag = "✓" if self.trust_level == "materialized" else "~"
        return (
            f"{self.table_name}[{trust_tag}] "
            f"rows={self.nb_rows} cols={self.cols[:6]}"
            + (f" sorted_by={self.sorted_by}" if self.sorted_by else "")
        )

    def context_summary(self) -> str:
        """Human-readable summary injected into the translation prompt."""
        lines = [f"Table `{self.table_name}` ({self.trust_level}):"]
        if self.cols:
            lines.append(f"  columns : {self.cols[:_MAX_COLS_IN_CONTEXT]}")
        if self.dtypes:
            dtype_str = ", ".join(
                f"{c}:{t}" for c, t in list(self.dtypes.items())[:10]
            )
            lines.append(f"  dtypes  : {dtype_str}")
        lines.append(f"  rows    : {self.nb_rows}")
        if self.sorted_by:
            lines.append(f"  sorted  : {self.sorted_by}")
        if self.frame is not None and not self.frame.empty:
            sample = self.frame.head(_MAX_ROWS_SHOWN).to_string(index=False)
            lines.append(f"  sample  :\n{sample}")
        return "\n".join(lines)


@dataclass
class CommittedStep:
    block_id:      uuid.UUID
    input_tables:  list[str]
    output_tables: list[str]


# ── tracker ───────────────────────────────────────────────────────────────────

class ExecutionStateTracker:
    """Tracks live DataFrame state across all translated partitions.

    Thread-safety: not thread-safe — designed for sequential pipeline use.
    If parallel translation is ever introduced, wrap mutations in a lock.
    """

    def __init__(self) -> None:
        self._tables:  dict[str, TableState] = {}
        self._history: list[CommittedStep]   = []

    # ── write ──────────────────────────────────────────────────────────────────

    def commit(
        self,
        table_name: str,
        frame: pd.DataFrame,
        *,
        produced_by: Optional[uuid.UUID] = None,
        sorted_by:   Optional[list[str]] = None,
    ) -> TableState:
        """Register a successfully executed output DataFrame.

        Args:
            table_name:  SAS dataset name (normalised to lowercase).
            frame:       The actual output DataFrame from TranslationPipeline.
            produced_by: block_id of the PartitionIR that produced this table.
            sorted_by:   BY columns if this table is known to be sorted.

        Returns:
            The new TableState for this table.
        """
        name = self._norm(table_name)
        work = frame.copy()
        work.columns = [str(c).lower() for c in work.columns]

        state = TableState(
            table_name  = name,
            trust_level = "materialized",
            cols        = list(work.columns),
            nb_rows     = len(work),
            sorted_by   = sorted_by or [],
            dtypes      = {c: str(t) for c, t in work.dtypes.items()},
            frame       = work,
            produced_by = produced_by,
        )
        self._tables[name] = state
        logger.info(
            "execution_state_commit",
            table=name,
            rows=state.nb_rows,
            cols=len(state.cols),
        )
        return state

    def infer(
        self,
        table_name: str,
        cols: list[str],
        *,
        sorted_by:   Optional[list[str]] = None,
        dtypes:      Optional[dict[str, str]] = None,
        produced_by: Optional[uuid.UUID] = None,
    ) -> TableState:
        """Register a schema-only (no real data) placeholder.

        Used when the SAS code is analysed statically but hasn't been executed.
        """
        name = self._norm(table_name)
        state = TableState(
            table_name  = name,
            trust_level = "inferred",
            cols        = [c.lower() for c in cols],
            nb_rows     = 0,
            sorted_by   = sorted_by or [],
            dtypes      = dtypes or {},
            frame       = None,
            produced_by = produced_by,
        )
        # Only register if not already materialized
        if name not in self._tables or self._tables[name].trust_level == "inferred":
            self._tables[name] = state
        return state

    def record_step(
        self,
        block_id:      uuid.UUID,
        input_tables:  list[str],
        output_tables: list[str],
    ) -> None:
        self._history.append(CommittedStep(
            block_id      = block_id,
            input_tables  = [self._norm(n) for n in input_tables],
            output_tables = [self._norm(n) for n in output_tables],
        ))

    # ── read ───────────────────────────────────────────────────────────────────

    def get_artifact(self, table_name: str) -> Optional[TableState]:
        return self._tables.get(self._norm(table_name))

    def get_context_for_partition(self, partition) -> str:  # type: ignore[type-arg]
        """Build a prompt-injectable context string for a partition.

        Looks at `partition.dependencies` (list of block_ids) and
        `partition.metadata.get('input_tables', [])` to find relevant tables.
        """
        input_names: list[str] = []

        # Try metadata first (set by FileProcessor)
        meta_inputs = partition.metadata.get("input_tables", [])
        if isinstance(meta_inputs, list):
            input_names = [self._norm(n) for n in meta_inputs]

        # Fallback: parse from source_code
        if not input_names:
            input_names = self._parse_input_names(partition.source_code or "")

        sections: list[str] = []
        for name in input_names:
            state = self._tables.get(name)
            if state is not None:
                sections.append(state.context_summary())

        if not sections:
            return ""

        header = f"## Upstream table state for chunk (trust=materialized where ✓):\n"
        return header + "\n\n".join(sections)

    def materialized_names(self) -> list[str]:
        """Return all table names that have real committed DataFrames."""
        return [
            name for name, state in self._tables.items()
            if state.trust_level == "materialized"
        ]

    def summary(self) -> str:
        lines = [
            f"ExecutionStateTracker: {len(self._tables)} tables, "
            f"{len(self._history)} committed steps"
        ]
        for name, state in sorted(self._tables.items()):
            lines.append(f"  {state.describe()}")
        return "\n".join(lines)

    # ── internal ───────────────────────────────────────────────────────────────

    @staticmethod
    def _norm(name: str) -> str:
        return str(name).strip().lower().split(".")[-1]

    @staticmethod
    def _parse_input_names(sas_code: str) -> list[str]:
        names: list[str] = []
        for pattern in (
            re.compile(r"\bset\s+([A-Za-z0-9_.]+)", re.IGNORECASE),
            re.compile(r"\bmerge\s+([A-Za-z0-9_. ]+?)(?:;|$)", re.IGNORECASE),
            re.compile(r"\bdata\s*=\s*([\w.]+)", re.IGNORECASE),
        ):
            for m in pattern.finditer(sas_code):
                for tok in m.group(1).split():
                    t = tok.strip().lower().split(".")[-1]
                    if t and re.match(r"^[a-z_]\w*$", t) and t not in names:
                        names.append(t)
        return names