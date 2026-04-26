"""Translation layer (L3) — TranslationAgent + ValidationAgent."""

__all__ = [
    "TranslationPipeline",
    "TranslationAgent",
    "ValidationAgent",
    "KBQueryClient",
]


def __getattr__(name: str):
    if name == "KBQueryClient":
        from partition.translation.kb_query import KBQueryClient

        return KBQueryClient
    if name == "TranslationAgent":
        from partition.translation.translation_agent import TranslationAgent

        return TranslationAgent
    if name == "TranslationPipeline":
        from partition.translation.translation_pipeline import TranslationPipeline

        return TranslationPipeline
    if name == "ValidationAgent":
        from partition.translation.validation_agent import ValidationAgent

        return ValidationAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
