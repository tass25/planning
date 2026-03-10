"""RAG sub-package — Static, GraphRAG, and Agentic retrieval paradigms.

Provides ``RAGRouter`` which selects the appropriate paradigm per partition
based on risk level, SCC membership, and dependency structure.
"""

from .router import RAGRouter
from .static_rag import StaticRAG
from .graph_rag import GraphRAG
from .agentic_rag import AgenticRAG

__all__ = ["RAGRouter", "StaticRAG", "GraphRAG", "AgenticRAG"]
