"""Azure Blob Storage service for SAS file uploads and pipeline outputs.

Graceful fallback: when AZURE_STORAGE_CONNECTION_STRING is not set the service
transparently falls back to local disk so development works without Azure.

Usage::

    from api.services.blob_service import blob_service

    # Upload
    blob_path = await blob_service.upload(file_id, filename, content_bytes)

    # Download to a local temp path (pipeline reads from here)
    local_path = await blob_service.download_to_temp(file_id, filename)

    # Delete all blobs for a conversion
    await blob_service.delete_folder(file_id)
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import structlog
from config.settings import settings

_log = structlog.get_logger("codara.blob")

# Local fallback directory (same as before Wave 2 Blob work)
_LOCAL_UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
_LOCAL_UPLOAD_DIR.mkdir(exist_ok=True)


class BlobStorageService:
    """Upload/download SAS files via Azure Blob Storage with local fallback."""

    def __init__(self) -> None:
        self._client = None
        self._container = settings.azure_storage_container
        self._enabled = False
        self._init()

    def _init(self) -> None:
        conn_str = settings.azure_storage_connection_string
        if not conn_str:
            _log.info(
                "blob_storage_disabled",
                reason="AZURE_STORAGE_CONNECTION_STRING not set — using local disk",
            )
            return
        try:
            from azure.storage.blob import BlobServiceClient

            self._client = BlobServiceClient.from_connection_string(conn_str)
            # Ensure container exists (idempotent)
            container = self._client.get_container_client(self._container)
            try:
                container.create_container()
                _log.info("blob_container_created", container=self._container)
            except Exception:
                pass  # already exists
            self._enabled = True
            _log.info("blob_storage_enabled", container=self._container)
        except Exception as exc:
            _log.warning("blob_storage_init_failed", error=str(exc), fallback="local disk")

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ── Upload ────────────────────────────────────────────────────────────────

    async def upload(self, file_id: str, filename: str, content: bytes) -> str:
        """Upload *content* to Blob Storage (or local disk).

        Returns the blob path (``file_id/filename``) or local absolute path.
        """
        if self._enabled:
            return await asyncio.to_thread(self._upload_sync, file_id, filename, content)
        return self._save_local(file_id, filename, content)

    def _upload_sync(self, file_id: str, filename: str, content: bytes) -> str:
        blob_name = f"{file_id}/{filename}"
        blob_client = self._client.get_blob_client(container=self._container, blob=blob_name)
        blob_client.upload_blob(content, overwrite=True)
        _log.info("blob_uploaded", blob=blob_name, size=len(content))
        return blob_name

    def _save_local(self, file_id: str, filename: str, content: bytes) -> str:
        dest = _LOCAL_UPLOAD_DIR / file_id / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        return str(dest)

    # ── Download ──────────────────────────────────────────────────────────────

    async def download_to_temp(self, file_id: str, filename: str) -> Path:
        """Download a blob to a local temp file and return its Path.

        The caller is responsible for deleting the temp file when done.
        If blob storage is disabled, returns the local upload path directly.
        """
        if self._enabled:
            return await asyncio.to_thread(self._download_sync, file_id, filename)
        local = _LOCAL_UPLOAD_DIR / file_id / filename
        if local.exists():
            return local
        raise FileNotFoundError(f"Local upload not found: {local}")

    def _download_sync(self, file_id: str, filename: str) -> Path:
        blob_name = f"{file_id}/{filename}"
        blob_client = self._client.get_blob_client(container=self._container, blob=blob_name)
        suffix = Path(filename).suffix
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        download = blob_client.download_blob()
        tmp.write(download.readall())
        tmp.close()
        _log.debug("blob_downloaded_to_temp", blob=blob_name, tmp=tmp.name)
        return Path(tmp.name)

    # ── List ──────────────────────────────────────────────────────────────────

    async def list_files(self, file_id: str) -> list[str]:
        """Return blob names (filenames only) under a given file_id prefix."""
        if self._enabled:
            return await asyncio.to_thread(self._list_sync, file_id)
        folder = _LOCAL_UPLOAD_DIR / file_id
        return [p.name for p in folder.glob("*.sas")] if folder.exists() else []

    def _list_sync(self, file_id: str) -> list[str]:
        prefix = f"{file_id}/"
        container = self._client.get_container_client(self._container)
        return [blob.name[len(prefix) :] for blob in container.list_blobs(name_starts_with=prefix)]

    # ── Delete ────────────────────────────────────────────────────────────────

    async def delete_folder(self, file_id: str) -> None:
        """Delete all blobs under *file_id* prefix (or the local folder)."""
        if self._enabled:
            await asyncio.to_thread(self._delete_sync, file_id)
        else:
            import shutil

            folder = _LOCAL_UPLOAD_DIR / file_id
            if folder.exists():
                shutil.rmtree(folder)

    def _delete_sync(self, file_id: str) -> None:
        prefix = f"{file_id}/"
        container = self._client.get_container_client(self._container)
        for blob in container.list_blobs(name_starts_with=prefix):
            container.delete_blob(blob.name)
        _log.info("blob_folder_deleted", file_id=file_id)


# Module-level singleton — import this everywhere
blob_service = BlobStorageService()
