"""Tests for DataLineageExtractor — table-level data lineage extraction."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from sas_converter.partition.db.sqlite_manager import (
    get_engine,
    init_db,
    get_session,
    DataLineageRow,
)
from sas_converter.partition.entry.data_lineage_extractor import DataLineageExtractor
from sas_converter.partition.models.file_metadata import FileMetadata


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_sas(tmp: Path, name: str, content: str) -> Path:
    """Write a SAS file and return its path."""
    p = tmp / name
    p.write_text(content, encoding="utf-8")
    return p


def _make_metadata(path: Path) -> FileMetadata:
    raw = path.read_bytes()
    import hashlib
    return FileMetadata(
        file_path=str(path),
        encoding="utf-8",
        content_hash=hashlib.sha256(raw).hexdigest(),
        file_size_bytes=len(raw),
        line_count=raw.decode().count("\n") + 1,
        lark_valid=True,
    )


def _run_extractor(files, engine):
    extractor = DataLineageExtractor()
    return asyncio.get_event_loop().run_until_complete(
        extractor.process(files, engine)
    )


def _query_rows(engine) -> list[DataLineageRow]:
    session = get_session(engine)
    rows = session.query(DataLineageRow).all()
    session.close()
    return rows


# Need to insert into file_registry first so FK is satisfied
def _insert_registry(engine, fm: FileMetadata):
    from sas_converter.partition.db.sqlite_manager import FileRegistryRow
    session = get_session(engine)
    session.add(FileRegistryRow(
        file_id=str(fm.file_id),
        file_path=fm.file_path,
        encoding=fm.encoding,
        content_hash=fm.content_hash,
        file_size_bytes=fm.file_size_bytes,
        line_count=fm.line_count,
        lark_valid=fm.lark_valid,
        lark_errors="",
        status="PENDING",
        error_log="",
        created_at=fm.created_at.isoformat(),
    ))
    session.commit()
    session.close()


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestDataLineageExtractor:
    """Five tests covering the core table-level lineage patterns."""

    def test_data_step_set_read(self, tmp_path):
        """DATA step with SET → detects TABLE_READ."""
        sas = _write_sas(tmp_path, "t1.sas", """\
DATA work.clean;
    SET raw.claims;
    x = 1;
RUN;
""")
        fm = _make_metadata(sas)
        engine = get_engine(str(tmp_path / "test.db"))
        init_db(engine)
        _insert_registry(engine, fm)

        result = _run_extractor([fm], engine)
        rows = _query_rows(engine)

        reads = [r for r in rows if r.lineage_type == "TABLE_READ"]
        writes = [r for r in rows if r.lineage_type == "TABLE_WRITE"]

        assert len(reads) == 1
        assert reads[0].source_dataset == "raw.claims"
        assert len(writes) == 1
        assert writes[0].target_dataset == "work.clean"
        assert result["total_reads"] == 1
        assert result["total_writes"] == 1

    def test_data_step_output_write(self, tmp_path):
        """DATA step output → detects TABLE_WRITE."""
        sas = _write_sas(tmp_path, "t2.sas", """\
DATA out.summary;
    SET staging.detail;
    total = price * qty;
RUN;
""")
        fm = _make_metadata(sas)
        engine = get_engine(str(tmp_path / "test.db"))
        init_db(engine)
        _insert_registry(engine, fm)

        _run_extractor([fm], engine)
        rows = _query_rows(engine)

        writes = [r for r in rows if r.lineage_type == "TABLE_WRITE"]
        assert len(writes) == 1
        assert writes[0].target_dataset == "out.summary"

    def test_proc_sql_from_join(self, tmp_path):
        """PROC SQL with FROM + JOIN → detects multiple TABLE_READ."""
        sas = _write_sas(tmp_path, "t3.sas", """\
PROC SQL;
    CREATE TABLE work.merged AS
    SELECT a.id, a.name, b.amount
    FROM src.customers AS a
    INNER JOIN src.orders AS b
    ON a.id = b.cust_id;
QUIT;
""")
        fm = _make_metadata(sas)
        engine = get_engine(str(tmp_path / "test.db"))
        init_db(engine)
        _insert_registry(engine, fm)

        _run_extractor([fm], engine)
        rows = _query_rows(engine)

        reads = [r for r in rows if r.lineage_type == "TABLE_READ"]
        read_datasets = sorted([r.source_dataset for r in reads])

        # FROM src.customers + JOIN src.orders = 2 reads
        assert "src.customers" in read_datasets
        assert "src.orders" in read_datasets
        assert len(reads) >= 2

    def test_create_table_write(self, tmp_path):
        """CREATE TABLE → detects TABLE_WRITE."""
        sas = _write_sas(tmp_path, "t4.sas", """\
PROC SQL;
    CREATE TABLE lib.report AS
    SELECT region, SUM(sales) AS total_sales
    FROM staging.transactions
    GROUP BY region;
QUIT;
""")
        fm = _make_metadata(sas)
        engine = get_engine(str(tmp_path / "test.db"))
        init_db(engine)
        _insert_registry(engine, fm)

        _run_extractor([fm], engine)
        rows = _query_rows(engine)

        writes = [r for r in rows if r.lineage_type == "TABLE_WRITE"]
        assert any(r.target_dataset == "lib.report" for r in writes)

    def test_multi_output_data_step(self, tmp_path):
        """DATA step with multiple output datasets → detects multiple TABLE_WRITE."""
        sas = _write_sas(tmp_path, "t5.sas", """\
DATA work.valid work.invalid;
    SET raw.transactions;
    IF amount > 0 THEN OUTPUT work.valid;
    ELSE OUTPUT work.invalid;
RUN;
""")
        fm = _make_metadata(sas)
        engine = get_engine(str(tmp_path / "test.db"))
        init_db(engine)
        _insert_registry(engine, fm)

        _run_extractor([fm], engine)
        rows = _query_rows(engine)

        writes = [r for r in rows if r.lineage_type == "TABLE_WRITE"]
        write_datasets = sorted([r.target_dataset for r in writes])

        assert "work.invalid" in write_datasets
        assert "work.valid" in write_datasets
        assert len(writes) >= 2
