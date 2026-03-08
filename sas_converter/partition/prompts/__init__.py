"""Structured prompt library for the SAS→Python translation pipeline.

All LLM prompts are centralised here as versioned Jinja2 templates,
loaded via ``PromptManager``.  Every prompt is parameterised — no
hard-coded strings in agent code.
"""

from .manager import PromptManager

__all__ = ["PromptManager"]
