"""ProjectConfigManager — YAML-based project configuration with dynamic hop cap.

Source config (project_config.yaml) is read-only. Runtime state is persisted
to a separate file (runtime_state.yaml) to avoid dirtying the repo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import structlog
import yaml

logger = structlog.get_logger()


class ProjectConfigManager:
    """Manage project-level configuration stored in a YAML file.

    Source config is immutable. Runtime-computed values (like hop cap)
    are persisted to a separate ``runtime_state.yaml`` under the same
    directory so they survive pipeline restarts without dirtying the repo.
    """

    # Resolve relative to sas_converter/ regardless of CWD
    _PKG_ROOT = Path(__file__).resolve().parent.parent.parent  # -> sas_converter/
    CONFIG_PATH = str(_PKG_ROOT / "config" / "project_config.yaml")
    _RUNTIME_STATE_FILE = "runtime_state.yaml"

    def __init__(self, config_path: Optional[str] = None):
        self.path = Path(config_path or self.CONFIG_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._runtime_path = self.path.parent / self._RUNTIME_STATE_FILE
        self._config: dict[str, Any] = self._load()
        self._runtime: dict[str, Any] = self._load_runtime()

    def _load(self) -> dict[str, Any]:
        if self.path.exists():
            with open(self.path) as f:
                return yaml.safe_load(f) or {}
        return {}

    def _load_runtime(self) -> dict[str, Any]:
        if self._runtime_path.exists():
            with open(self._runtime_path) as f:
                return yaml.safe_load(f) or {}
        return {}

    def _save_runtime(self):
        """Persist runtime state (not source config) to a separate file."""
        with open(self._runtime_path, "w") as f:
            yaml.dump(self._runtime, f, default_flow_style=False)
        logger.debug("runtime_state_saved", path=str(self._runtime_path))

    # ------------------------------------------------------------------
    # Graph / hop-cap helpers
    # ------------------------------------------------------------------

    def set_max_hop(self, max_hop: int):
        """Set the dynamic hop cap for NetworkX traversals (runtime state)."""
        self._runtime.setdefault("graph", {})
        self._runtime["graph"]["max_hop"] = max_hop
        self._save_runtime()

    def get_max_hop(self) -> int:
        """Return the stored hop cap (runtime override > config > default 3)."""
        runtime_hop = self._runtime.get("graph", {}).get("max_hop")
        if runtime_hop is not None:
            return runtime_hop
        return self._config.get("graph", {}).get("max_hop", 3)

    # ------------------------------------------------------------------
    # Generic accessors
    # ------------------------------------------------------------------

    def set(self, key: str, value: Any):
        """Set a runtime value (persisted to runtime_state.yaml, not source config)."""
        self._runtime[key] = value
        self._save_runtime()

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value: runtime override > source config > default."""
        if key in self._runtime:
            return self._runtime[key]
        return self._config.get(key, default)
