"""PromptManager — load, render, and version prompt templates.

Templates live as plain-text files under ``prompts/templates/``.
They use Jinja2 syntax for variable injection.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATES_DIR = Path(__file__).parent / "templates"


class PromptManager:
    """Centralised prompt rendering engine.

    Usage::

        pm = PromptManager()
        prompt = pm.render("translation_static", sas_code=code, ...)
    """

    VERSION = "1.0.0"

    def __init__(self, templates_dir: Path | None = None):
        self._dir = templates_dir or _TEMPLATES_DIR
        self._env = Environment(
            loader=FileSystemLoader(str(self._dir)),
            autoescape=select_autoescape([]),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

    def render(self, template_name: str, **kwargs: Any) -> str:
        """Render a named template with the given variables."""
        tpl = self._env.get_template(f"{template_name}.j2")
        return tpl.render(**kwargs)

    def list_templates(self) -> list[str]:
        """Return available template names (without .j2 extension)."""
        return sorted(
            p.stem for p in self._dir.glob("*.j2")
        )
