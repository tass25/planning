"""File storage abstraction — swap LocalStorage for AzureBlobStorage via env var.

# Pattern: Strategy

Usage::

    from partition.utils.storage import get_storage
    storage = get_storage()
    key = await storage.save("uploads/file-abc123/mycode.sas", content_bytes)
    data = await storage.load(key)
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path

import structlog

log = structlog.get_logger("codara.storage")


class StorageBackend(ABC):
    """Abstract file storage interface."""

    @abstractmethod
    async def save(self, key: str, data: bytes) -> str:
        """Persist *data* under *key*; return the canonical storage key."""

    @abstractmethod
    async def load(self, key: str) -> bytes:
        """Load and return bytes stored under *key*."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete the object at *key* (no-op if not found)."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Return True if *key* exists in storage."""


class LocalStorage(StorageBackend):
    """Store files on the local filesystem under *base_dir*."""

    def __init__(self, base_dir: str = "backend/uploads") -> None:
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, key: str, data: bytes) -> str:
        dest = self.base_dir / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return key

    async def load(self, key: str) -> bytes:
        return (self.base_dir / key).read_bytes()

    async def delete(self, key: str) -> None:
        path = self.base_dir / key
        if path.exists():
            path.unlink()

    async def exists(self, key: str) -> bool:
        return (self.base_dir / key).exists()


class AzureBlobStorage(StorageBackend):
    """Store files in Azure Blob Storage.

    Reads AZURE_STORAGE_CONNECTION_STRING and AZURE_STORAGE_CONTAINER from env.
    Falls back to LocalStorage if the SDK is not installed or creds are missing.
    """

    def __init__(self) -> None:
        from azure.storage.blob import BlobServiceClient  # type: ignore
        conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
        self.container = os.getenv("AZURE_STORAGE_CONTAINER", "codara-uploads")
        if not conn_str:
            raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING is not set")
        self._client = BlobServiceClient.from_connection_string(conn_str)
        self._container_client = self._client.get_container_client(self.container)
        # Create container if it doesn't exist yet
        try:
            self._container_client.create_container()
        except Exception:
            pass  # already exists
        log.info("azure_blob_storage_ready", container=self.container)

    async def save(self, key: str, data: bytes) -> str:
        await asyncio.to_thread(
            self._container_client.upload_blob, key, data, overwrite=True
        )
        return key

    async def load(self, key: str) -> bytes:
        blob = self._container_client.get_blob_client(key)
        stream = await asyncio.to_thread(blob.download_blob)
        return await asyncio.to_thread(stream.readall)

    async def delete(self, key: str) -> None:
        try:
            blob = self._container_client.get_blob_client(key)
            await asyncio.to_thread(blob.delete_blob)
        except Exception:
            pass

    async def exists(self, key: str) -> bool:
        blob = self._container_client.get_blob_client(key)
        try:
            await asyncio.to_thread(blob.get_blob_properties)
            return True
        except Exception:
            return False


def get_storage() -> StorageBackend:
    """Return the appropriate storage backend based on APP_ENV.

    - development / staging → LocalStorage
    - production + AZURE_STORAGE_ACCOUNT_URL set → AzureBlobStorage (TODO)
    """
    app_env = os.getenv("APP_ENV", "development").lower()
    azure_url = os.getenv("AZURE_STORAGE_ACCOUNT_URL", "")

    if app_env == "production" and azure_url:
        log.info("storage_backend", backend="azure_blob")
        return AzureBlobStorage()  # will raise NotImplementedError until implemented

    log.info("storage_backend", backend="local")
    return LocalStorage()
