"""PersistenceAgent (#10) — Write partitions to SQLite with dedup."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import structlog

from partition.base_agent import BaseAgent
from partition.db.sqlite_manager import (
    FileRegistryRow,
    PartitionIRRow,
    get_engine,
    init_db,
    get_session,
)

logger = structlog.get_logger()


class PersistenceAgent(BaseAgent):
    """Agent #10 — Persist PartitionIR objects to SQLite.

    Features:
        - content_hash–based dedup (INSERT OR IGNORE semantics via check)
        - Batch writes with configurable flush size
        - Parquet fallback stub for batches ≥ PARQUET_THRESHOLD
    """

    agent_name = "PersistenceAgent"

    PARQUET_THRESHOLD = 10_000  # Switch to Parquet for very large batches

    def __init__(
        self,
        db_url: str | None = None,
        trace_id=None,
    ):
        super().__init__(trace_id)
        # Accept either "sqlite:///path" or plain path
        if db_url and db_url.startswith("sqlite"):
            self.engine = get_engine.__wrapped__(db_url) if hasattr(get_engine, '__wrapped__') else self._engine_from_url(db_url)
        else:
            db_path = db_url or "file_registry.db"
            # Strip sqlite:/// prefix if accidentally doubled
            if db_path.startswith("sqlite:///"):
                db_path = db_path[len("sqlite:///"):]
            self.engine = get_engine(db_path)

        init_db(self.engine)
        self.logger.info("persistence_agent_init", engine=str(self.engine.url))

    @staticmethod
    def _engine_from_url(url: str):
        """Create an engine directly from a full SQLAlchemy URL."""
        from sqlalchemy import create_engine as _ce, event as _ev
        engine = _ce(url, echo=False)

        @_ev.listens_for(engine, "connect")
        def _set_pragma(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        return engine

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    async def process(
        self,
        partitions: list,
        file_id: str | None = None,
    ) -> int:
        """Persist a list of partition-like objects to SQLite.

        Dedup: Rows with an existing content_hash are silently skipped.

        Returns:
            Number of rows actually written (after dedup).
        """
        if not partitions:
            return 0

        # Parquet fallback for very large batches
        if len(partitions) >= self.PARQUET_THRESHOLD:
            return self._write_parquet(partitions)

        session = get_session(self.engine)
        written = 0
        try:
            # Fetch existing hashes for dedup
            existing_hashes: set[str] = set()
            try:
                rows = session.query(PartitionIRRow.content_hash).all()
                existing_hashes = {r[0] for r in rows}
            except Exception:
                pass  # Table may be empty

            # Auto-ensure file_registry entries exist (FK requirement)
            seen_file_ids: set[str] = set()
            for p in partitions:
                fid = str(getattr(p, 'source_file_id', None) or getattr(p, 'file_id', ''))
                if fid and fid not in seen_file_ids:
                    existing = session.query(FileRegistryRow).filter_by(file_id=fid).first()
                    if not existing:
                        session.add(FileRegistryRow(
                            file_id=fid,
                            file_path=str(getattr(p, 'file_path', f'unknown/{fid}.sas')),
                            encoding='utf-8',
                            content_hash=fid,
                            created_at=datetime.now(timezone.utc).isoformat(),
                        ))
                    seen_file_ids.add(fid)
            session.flush()  # Ensure FKs are available

            for p in partitions:
                content_hash = self._compute_hash(p)
                if content_hash in existing_hashes:
                    self.logger.debug("dedup_skip", content_hash=content_hash[:12])
                    continue

                row = PartitionIRRow(
                    partition_id=str(getattr(p, 'partition_id', None) or getattr(p, 'block_id', uuid4())),
                    source_file_id=str(getattr(p, 'source_file_id', None) or getattr(p, 'file_id', '')),
                    partition_type=getattr(p.partition_type, 'value', str(p.partition_type)),
                    risk_level=getattr(p.risk_level, 'value', str(getattr(p, 'risk_level', 'UNCERTAIN'))),
                    conversion_status=getattr(
                        getattr(p, 'conversion_status', None), 'value', 'HUMAN_REVIEW'
                    ),
                    content_hash=content_hash,
                    complexity_score=getattr(p, 'complexity_score', 0.0),
                    calibration_confidence=getattr(p, 'calibration_confidence', 0.0),
                    strategy=getattr(
                        getattr(p, 'strategy', None), 'value',
                        str(getattr(p, 'strategy', 'FLAT_PARTITION'))
                    ),
                    line_start=getattr(p, 'line_start', 0),
                    line_end=getattr(p, 'line_end', 0),
                    control_depth=getattr(p, 'control_depth', 0),
                    has_macros=bool(getattr(p, 'has_macros', False)),
                    has_nested_sql=bool(getattr(p, 'has_nested_sql', False)),
                    raw_code=getattr(p, 'raw_code', getattr(p, 'source_code', '')),
                    raptor_leaf_id=getattr(p, 'raptor_leaf_id', None),
                    raptor_cluster_id=getattr(p, 'raptor_cluster_id', None),
                    raptor_root_id=getattr(p, 'raptor_root_id', None),
                    scc_id=getattr(p, 'scc_id', None),
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
                session.add(row)
                existing_hashes.add(content_hash)
                written += 1

            session.commit()
            self.logger.info(
                "persistence_write",
                total=len(partitions),
                written=written,
                deduped=len(partitions) - written,
            )
        except Exception as exc:
            session.rollback()
            self.logger.error("persistence_write_failed", error=str(exc))
            raise
        finally:
            session.close()

        return written

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_hash(partition) -> str:
        """SHA-256 of the raw code content for dedup."""
        code = getattr(partition, 'raw_code', None) or getattr(partition, 'source_code', '')
        return hashlib.sha256(code.encode()).hexdigest()

    def _write_parquet(self, partitions: list) -> int:
        """Parquet fallback for batches ≥ PARQUET_THRESHOLD.

        Writes to ``partition_ir_overflow.parquet`` and logs a warning.
        This is a stub — full Parquet integration is deferred to Week 9.
        """
        import pyarrow as pa
        import pyarrow.parquet as pq

        records = []
        for p in partitions:
            records.append({
                "partition_id": str(getattr(p, 'partition_id', None) or getattr(p, 'block_id', '')),
                "source_file_id": str(getattr(p, 'source_file_id', None) or getattr(p, 'file_id', '')),
                "partition_type": getattr(p.partition_type, 'value', ''),
                "content_hash": self._compute_hash(p),
                "raw_code": getattr(p, 'raw_code', getattr(p, 'source_code', '')),
            })
        table = pa.table(records)
        pq.write_table(table, "partition_ir_overflow.parquet")
        self.logger.warning(
            "parquet_fallback",
            n_records=len(records),
            path="partition_ir_overflow.parquet",
        )
        return len(records)
