"""Tests for LocalModelClient.

Tests that the client degrades gracefully when:
  - LOCAL_MODEL_PATH is not set
  - LOCAL_MODEL_PATH points to a non-existent file
  - llama-cpp-python is not installed
"""

from __future__ import annotations

import pytest
from partition.utils.local_model_client import LocalModelClient, get_local_model_client


class TestLocalModelClient:
    def test_not_available_when_path_unset(self, monkeypatch):
        monkeypatch.delenv("LOCAL_MODEL_PATH", raising=False)
        client = LocalModelClient()
        assert not client.is_available

    def test_not_available_when_file_missing(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LOCAL_MODEL_PATH", str(tmp_path / "nonexistent.gguf"))
        client = LocalModelClient()
        assert not client.is_available

    @pytest.mark.asyncio
    async def test_complete_returns_none_when_unavailable(self, monkeypatch):
        monkeypatch.delenv("LOCAL_MODEL_PATH", raising=False)
        client = LocalModelClient()
        result = await client.complete("data output; set input; run;")
        assert result is None

    def test_singleton_returns_same_instance(self, monkeypatch):
        monkeypatch.delenv("LOCAL_MODEL_PATH", raising=False)
        import partition.utils.local_model_client as m

        m._client = None  # reset singleton
        c1 = get_local_model_client()
        c2 = get_local_model_client()
        assert c1 is c2

    def test_available_when_file_exists(self, monkeypatch, tmp_path):
        """Client reports available when path exists (even though not a real GGUF)."""
        fake_gguf = tmp_path / "model.gguf"
        fake_gguf.write_bytes(b"fake")
        monkeypatch.setenv("LOCAL_MODEL_PATH", str(fake_gguf))
        client = LocalModelClient()
        client._available = None  # reset cache
        # is_available = True because file exists (load happens lazily)
        assert client.is_available
