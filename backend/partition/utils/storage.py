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

    # STUB: Azure Blob Storage not yet implemented.
    # TODO: implement using azure-storage-blob SDK.
    # Required env vars: AZURE_STORAGE_ACCOUNT_URL, AZURE_STORAGE_CONTAINER
    # Switch to this backend by setting APP_ENV=production in .env.
    """

    def __init__(self) -> None:
        raise NotImplementedError(
            "AzureBlobStorage is not yet implemented. "
            "Set APP_ENV=development to use LocalStorage."
        )

    async def save(self, key: str, data: bytes) -> str:  # pragma: no cover
        raise NotImplementedError

    async def load(self, key: str) -> bytes:  # pragma: no cover
        raise NotImplementedError

    async def delete(self, key: str) -> None:  # pragma: no cover
        raise NotImplementedError

    async def exists(self, key: str) -> bool:  # pragma: no cover
        raise NotImplementedError


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
