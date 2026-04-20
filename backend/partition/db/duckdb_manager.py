"""DuckDB analytics table management — all 7 tables."""

from __future__ import annotations

import duckdb
import structlog

logger = structlog.get_logger()

DB_PATH = "data/analytics.duckdb"


def init_all_duckdb_tables(db_path: str = DB_PATH):
    """Initialize all DuckDB analytics tables.

    Tables:
        1. llm_audit        — every LLM call logged
        2. calibration_log  — ECE per training run (from Week 4)
        3. ablation_results — RAPTOR vs flat study
        4. quality_metrics  — translation quality per batch
        5. feedback_log     — correction tracking
        6. kb_changelog     — KB versioning audit trail
        7. conversion_reports — per-file report metadata
    """
    con = duckdb.connect(db_path)

    # Table 1: llm_audit
    con.execute("""
        CREATE TABLE IF NOT EXISTS llm_audit (
            call_id       VARCHAR PRIMARY KEY,
            agent_name    VARCHAR,
            model_name    VARCHAR,
            prompt_hash   VARCHAR,
            response_hash VARCHAR,
            latency_ms    DOUBLE,
            success       BOOLEAN,
            error_msg     VARCHAR,
            tier          VARCHAR,
            timestamp     TIMESTAMP DEFAULT NOW()
        )
    """)

    # Table 2: calibration_log
    con.execute("""
        CREATE TABLE IF NOT EXISTS calibration_log (
            log_id        VARCHAR PRIMARY KEY,
            ece_score     DOUBLE,
            n_samples     INTEGER,
            n_train       INTEGER,
            model_version VARCHAR,
            created_at    TIMESTAMP DEFAULT NOW()
        )
    """)

    # Table 3: ablation_results
    con.execute("""
        CREATE TABLE IF NOT EXISTS ablation_results (
            run_id           VARCHAR,
            file_id          VARCHAR,
            query_id         VARCHAR,
            index_type       VARCHAR,
            hit_at_5         BOOLEAN,
            reciprocal_rank  DOUBLE,
            query_latency_ms DOUBLE,
            complexity_tier  VARCHAR,
            depth_level      INTEGER,
            created_at       TIMESTAMP,
            PRIMARY KEY (run_id, file_id, query_id, index_type)
        )
    """)

    # Table 4: quality_metrics
    con.execute("""
        CREATE TABLE IF NOT EXISTS quality_metrics (
            metric_id           VARCHAR PRIMARY KEY,
            batch_id            VARCHAR,
            n_evaluated         INTEGER,
            success_rate        DOUBLE,
            partial_rate        DOUBLE,
            human_review_rate   DOUBLE,
            avg_llm_confidence  DOUBLE,
            avg_retry_count     DOUBLE,
            failure_mode_dist   VARCHAR,
            kb_size             INTEGER,
            created_at          TIMESTAMP
        )
    """)

    # Table 5: feedback_log
    con.execute("""
        CREATE TABLE IF NOT EXISTS feedback_log (
            feedback_id         VARCHAR PRIMARY KEY,
            conversion_id       VARCHAR,
            partition_id        VARCHAR,
            correction_source   VARCHAR,
            original_status     VARCHAR,
            new_kb_example_id   VARCHAR,
            verifier_confidence DOUBLE,
            accepted            BOOLEAN,
            rejection_reason    VARCHAR,
            created_at          TIMESTAMP DEFAULT NOW()
        )
    """)

    # Table 6: kb_changelog
    con.execute("""
        CREATE TABLE IF NOT EXISTS kb_changelog (
            changelog_id        VARCHAR PRIMARY KEY,
            example_id          VARCHAR NOT NULL,
            action              VARCHAR NOT NULL,
            old_version         INTEGER,
            new_version         INTEGER NOT NULL,
            author              VARCHAR NOT NULL,
            diff_summary        VARCHAR,
            created_at          TIMESTAMP DEFAULT NOW()
        )
    """)

    # Table 7: conversion_reports
    con.execute("""
        CREATE TABLE IF NOT EXISTS conversion_reports (
            report_id           VARCHAR PRIMARY KEY,
            source_file_id      VARCHAR NOT NULL,
            total_blocks        INTEGER,
            success_count       INTEGER,
            partial_count       INTEGER,
            failed_count        INTEGER,
            human_review_count  INTEGER,
            validation_pass     INTEGER,
            validation_fail     INTEGER,
            codebleu_mean       DOUBLE,
            failure_mode_dist   VARCHAR,
            report_md_path      VARCHAR,
            report_html_path    VARCHAR,
            created_at          TIMESTAMP DEFAULT NOW()
        )
    """)

    con.close()
    logger.info("duckdb_all_tables_initialized", db_path=db_path)


# ── Schema versioning ────────────────────────────────────────────────────────

DUCKDB_SCHEMA_VERSION = 1


def check_duckdb_schema(db_path: str = DB_PATH) -> int:
    """Ensure schema_version table exists and return current version."""
    con = duckdb.connect(db_path)
    con.execute(
        "CREATE TABLE IF NOT EXISTS schema_version "
        "(version INTEGER NOT NULL, applied_at TIMESTAMP DEFAULT NOW())"
    )
    row = con.execute("SELECT MAX(version) FROM schema_version").fetchone()
    current = (row[0] or 0) if row else 0
    if current < DUCKDB_SCHEMA_VERSION:
        con.execute(
            "INSERT INTO schema_version VALUES (?, NOW())",
            [DUCKDB_SCHEMA_VERSION],
        )
    con.close()
    return max(current, DUCKDB_SCHEMA_VERSION)


def log_llm_call(
    db_path: str,
    call_id: str,
    agent_name: str,
    model_name: str,
    prompt_hash: str,
    response_hash: str,
    latency_ms: float,
    success: bool,
    error_msg: str | None = None,
    tier: str | None = None,
):
    """Log an LLM call to the audit table."""
    con = duckdb.connect(db_path)
    con.execute(
        """
        INSERT INTO llm_audit
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())
        """,
        [
            call_id,
            agent_name,
            model_name,
            prompt_hash,
            response_hash,
            latency_ms,
            success,
            error_msg,
            tier,
        ],
    )
    con.close()
