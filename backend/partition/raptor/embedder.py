"""NomicEmbedder — 768-dim embeddings via Nomic Embed v1.5."""

from __future__ import annotations

import hashlib
from collections import OrderedDict

import numpy as np
import structlog

logger = structlog.get_logger()

try:
    from sentence_transformers import SentenceTransformer as _SentenceTransformer

    _ST_AVAILABLE = True
except Exception:  # ImportError or missing tf_keras / tensorflow cascade
    _SentenceTransformer = None  # type: ignore[assignment]
    _ST_AVAILABLE = False
    logger.warning(
        "sentence_transformers_unavailable",
        hint="pip install sentence-transformers tf-keras",
    )


class NomicEmbedder:
    """Embed SAS code blocks using Nomic Embed v1.5 (768-dim).

    Nomic Embed v1.5 requires task-specific prefixes:
    - ``search_document:`` when indexing (embed_batch / embed)
    - ``search_query:``    when querying at retrieval time (embed_query)

    Omitting the prefix degrades retrieval quality by ~15%.
    """

    MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"
    DIM = 768
    CACHE_MAXSIZE = 10_000

    def __init__(self, device: str = "cpu"):
        """
        Args:
            device: 'cpu' or 'cuda'. Pass ``torch.cuda.is_available()``
                    result at call-site when GPU is available.
        """
        if not _ST_AVAILABLE:
            raise RuntimeError(
                "sentence-transformers is not importable. "
                "Install missing dependency: pip install tf-keras"
            )
        self.model = _SentenceTransformer(
            self.MODEL_NAME,
            device=device,
            # SECURITY: trust_remote_code is required by nomic-embed-text-v1.5
            # because the model ships custom mean-pooling code on HuggingFace.
            # The model is published by Nomic AI (verified org) and pinned by
            # name. This flag is safe for this specific, trusted model.
            trust_remote_code=True,
        )
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        logger.info("nomic_embedder_init", model=self.MODEL_NAME, device=device)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed(self, text: str) -> list[float]:
        """Embed a single text. SHA-256 cache avoids re-embedding duplicates."""
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        if text_hash in self._cache:
            self._cache.move_to_end(text_hash)
            return self._cache[text_hash].tolist()

        prefixed = f"search_document: {text}"
        embedding = self.model.encode(prefixed, normalize_embeddings=True)
        self._cache[text_hash] = embedding
        if len(self._cache) > self.CACHE_MAXSIZE:
            self._cache.popitem(last=False)
        return embedding.tolist()

    def embed_batch(
        self,
        texts: list[str],
        batch_size: int = 32,
    ) -> list[list[float]]:
        """Embed multiple texts with batching and SHA-256 cache."""
        results: list[tuple[int, list[float]]] = []
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        for i, text in enumerate(texts):
            text_hash = hashlib.sha256(text.encode()).hexdigest()
            if text_hash in self._cache:
                self._cache.move_to_end(text_hash)
                results.append((i, self._cache[text_hash].tolist()))
            else:
                uncached_indices.append(i)
                uncached_texts.append(f"search_document: {text}")

        if uncached_texts:
            embeddings = self.model.encode(
                uncached_texts,
                batch_size=batch_size,
                normalize_embeddings=True,
                show_progress_bar=len(uncached_texts) > 100,
            )
            for idx, emb, raw_text in zip(
                uncached_indices, embeddings, texts  # raw_text for cache key
            ):
                text_hash = hashlib.sha256(raw_text.encode()).hexdigest()
                self._cache[text_hash] = emb
                if len(self._cache) > self.CACHE_MAXSIZE:
                    self._cache.popitem(last=False)
                results.append((idx, emb.tolist()))

        results.sort(key=lambda x: x[0])
        logger.debug(
            "embed_batch_done",
            total=len(texts),
            from_cache=len(texts) - len(uncached_texts),
        )
        return [r[1] for r in results]

    def embed_query(self, query: str) -> list[float]:
        """Embed a retrieval query (uses 'search_query:' prefix per Nomic spec)."""
        prefixed = f"search_query: {query}"
        return self.model.encode(prefixed, normalize_embeddings=True).tolist()

    @property
    def cache_size(self) -> int:
        """Number of texts currently cached."""
        return len(self._cache)


# ── Module-level singleton ────────────────────────────────────────────────────
# The sentence-transformers model is ~270 MB and takes ~10s to load on first
# call.  All agents share this one instance so concurrent pipelines don't each
# load their own copy.

_embedder: NomicEmbedder | None = None


def get_embedder(device: str = "cpu") -> NomicEmbedder:
    """Return the shared NomicEmbedder singleton (created lazily on first call).

    Args:
        device: ``"cpu"`` or ``"cuda"``. Only used on the very first call;
                subsequent calls return the already-initialised instance.
    """
    global _embedder  # noqa: PLW0603
    if _embedder is None:
        _embedder = NomicEmbedder(device=device)
    return _embedder
