"""Backpressure queue factory — sizes the asyncio.Queue based on file size."""

from __future__ import annotations

import asyncio

from partition.models.file_metadata import FileMetadata


def create_queue(file_meta: FileMetadata) -> asyncio.Queue:
    """Return an ``asyncio.Queue`` whose *maxsize* adapts to the source file.

    * > 500 MB → ``maxsize=10``  (sequential-processing mode)
    * > 100 MB → ``maxsize=50``  (reduced concurrency)
    * Otherwise → ``maxsize=200`` (standard throughput)
    """
    size_bytes = file_meta.file_size_bytes
    if size_bytes > 500_000_000:
        maxsize = 10
    elif size_bytes > 100_000_000:
        maxsize = 50
    else:
        maxsize = 200
    return asyncio.Queue(maxsize=maxsize)
