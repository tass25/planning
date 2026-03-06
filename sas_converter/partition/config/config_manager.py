"""ProjectConfigManager — YAML-based project configuration with dynamic hop cap."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml
import structlog

logger = structlog.get_logger()


class ProjectConfigManager:
    """Manage project-level configuration stored in a YAML file.

    Used to persist runtime-computed values like the dynamic hop cap
    so they survive pipeline restarts.
    """

    # Resolve relative to sas_converter/ regardless of CWD
    _PKG_ROOT = Path(__file__).resolve().parent.parent.parent  # -> sas_converter/
    CONFIG_PATH = str(_PKG_ROOT / "config" / "project_config.yaml")

    def __init__(self, config_path: Optional[str] = None):
        self.path = Path(config_path or self.CONFIG_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._config: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if self.path.exists():
            with open(self.path) as f:
                return yaml.safe_load(f) or {}
        return {}

    def save(self):
        """Persist current config to YAML."""
        with open(self.path, "w") as f:
            yaml.dump(self._config, f, default_flow_style=False)
        logger.debug("config_saved", path=str(self.path))

    # ------------------------------------------------------------------
    # Graph / hop-cap helpers
    # ------------------------------------------------------------------

    def set_max_hop(self, max_hop: int):
        """Set the dynamic hop cap for NetworkX traversals."""
        self._config.setdefault("graph", {})
        self._config["graph"]["max_hop"] = max_hop
        self.save()

    def get_max_hop(self) -> int:
        """Return the stored hop cap (default 3)."""
        return self._config.get("graph", {}).get("max_hop", 3)

    # ------------------------------------------------------------------
    # Generic accessors
    # ------------------------------------------------------------------

    def set(self, key: str, value: Any):
        self._config[key] = value
        self.save()

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)
