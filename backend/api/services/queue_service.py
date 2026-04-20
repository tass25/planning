"""Azure Queue Storage service for durable pipeline job queuing.

Graceful fallback: when AZURE_STORAGE_CONNECTION_STRING is not set, jobs
are executed directly in a background thread (current behaviour) — no
Azure dependency required for local development.

Architecture
------------
Producer (API request) → enqueue_job() → Azure Queue
Consumer (worker thread started at startup) → dequeue_job() → run_pipeline_sync()

The worker loop runs in a daemon thread so it exits cleanly with the process.
Visibility timeout: 5 minutes — if the worker crashes mid-job, the message
reappears after 5 minutes and is retried automatically by Azure.

Usage::

    # In main.py startup:
    from api.services.queue_service import queue_service
    queue_service.start_worker()

    # In conversions route instead of BackgroundTasks:
    queue_service.enqueue_job(conv_id, file_id, filename, db_path)
"""

from __future__ import annotations

import base64
import json
import threading
import time

import structlog
from config.settings import settings

_log = structlog.get_logger("codara.queue")

_VISIBILITY_TIMEOUT_S = 300  # 5 minutes — job must complete within this
_POLL_INTERVAL_S = 2  # how often the worker polls when idle
_MAX_DEQUEUE_COUNT = 5  # after 5 failed attempts, move to dead-letter
_WORKER_SLEEP_ON_ERR = 10  # seconds to sleep after an unexpected worker error


class PipelineQueueService:
    """Enqueue and consume pipeline jobs via Azure Queue Storage.

    Falls back to direct BackgroundTask execution when Azure is not configured.
    """

    def __init__(self) -> None:
        self._client = None
        self._queue_name = settings.azure_queue_name
        self._enabled = False
        self._worker_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._init()

    def _init(self) -> None:
        conn_str = settings.azure_storage_connection_string
        if not conn_str:
            _log.info(
                "queue_service_disabled",
                reason="AZURE_STORAGE_CONNECTION_STRING not set — using BackgroundTasks",
            )
            return
        try:
            from azure.storage.queue import QueueServiceClient

            svc = QueueServiceClient.from_connection_string(conn_str)
            self._client = svc.get_queue_client(self._queue_name)
            try:
                self._client.create_queue()
                _log.info("queue_created", queue=self._queue_name)
            except Exception:
                pass  # already exists
            self._enabled = True
            _log.info("queue_service_enabled", queue=self._queue_name)
        except Exception as exc:
            _log.warning("queue_service_init_failed", error=str(exc), fallback="BackgroundTasks")

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ── Producer ──────────────────────────────────────────────────────────────

    def enqueue_job(
        self,
        conversion_id: str,
        file_id: str,
        filename: str,
        db_path: str,
    ) -> bool:
        """Enqueue a pipeline job. Returns True if queued, False if direct execution needed."""
        if not self._enabled:
            return False

        payload = json.dumps(
            {
                "conversion_id": conversion_id,
                "file_id": file_id,
                "filename": filename,
                "db_path": db_path,
            }
        )
        # Azure Queue requires base64-encoded messages
        encoded = base64.b64encode(payload.encode()).decode()
        try:
            self._client.send_message(encoded, visibility_timeout=0)
            _log.info("job_enqueued", conversion_id=conversion_id, queue=self._queue_name)
            return True
        except Exception as exc:
            _log.error("job_enqueue_failed", conversion_id=conversion_id, error=str(exc))
            return False

    # ── Consumer / Worker ─────────────────────────────────────────────────────

    def start_worker(self) -> None:
        """Start the background consumer thread. Idempotent — safe to call multiple times."""
        if not self._enabled:
            _log.info("queue_worker_skipped", reason="queue not enabled")
            return
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name="codara-queue-worker",
            daemon=True,
        )
        self._worker_thread.start()
        _log.info("queue_worker_started", queue=self._queue_name)

    def stop_worker(self) -> None:
        """Signal the worker to stop. Used in tests and graceful shutdown."""
        self._stop_event.set()

    def _worker_loop(self) -> None:
        """Poll the queue and process jobs until stop_event is set."""
        from api.services.pipeline_service import run_pipeline_sync

        _log.info("queue_worker_running")
        while not self._stop_event.is_set():
            try:
                messages = self._client.receive_messages(
                    max_messages=1,
                    visibility_timeout=_VISIBILITY_TIMEOUT_S,
                )
                msg = next(iter(messages), None)
                if msg is None:
                    self._stop_event.wait(timeout=_POLL_INTERVAL_S)
                    continue

                # Decode and parse
                try:
                    raw = base64.b64decode(msg.content).decode()
                    job = json.loads(raw)
                except Exception as exc:
                    _log.error(
                        "queue_message_decode_failed", error=str(exc), content=msg.content[:200]
                    )
                    self._client.delete_message(msg)
                    continue

                # Guard against poison messages
                if msg.dequeue_count > _MAX_DEQUEUE_COUNT:
                    _log.error(
                        "job_dead_lettered",
                        conversion_id=job.get("conversion_id"),
                        dequeue_count=msg.dequeue_count,
                    )
                    self._client.delete_message(msg)
                    continue

                conversion_id = job.get("conversion_id", "unknown")
                _log.info(
                    "job_processing", conversion_id=conversion_id, dequeue_count=msg.dequeue_count
                )

                try:
                    run_pipeline_sync(
                        conversion_id=job["conversion_id"],
                        file_id=job["file_id"],
                        filename=job["filename"],
                        db_path=job["db_path"],
                    )
                    _log.info("job_completed", conversion_id=conversion_id)
                except Exception as exc:
                    _log.error("job_failed", conversion_id=conversion_id, error=str(exc))
                    # Let message become visible again after visibility_timeout
                    # so Azure retries it automatically — do NOT delete it here.
                    time.sleep(_POLL_INTERVAL_S)
                    continue

                # Success — delete the message from the queue
                self._client.delete_message(msg)

            except Exception as exc:
                _log.error("queue_worker_error", error=str(exc))
                self._stop_event.wait(timeout=_WORKER_SLEEP_ON_ERR)

        _log.info("queue_worker_stopped")


# Module-level singleton
queue_service = PipelineQueueService()
