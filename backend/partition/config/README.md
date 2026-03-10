# Configuration

YAML-backed project configuration with runtime persistence.

## Files

| File | Description |
|------|-------------|
| `config_manager.py` | `ProjectConfigManager` — YAML read/write with generic `get()`/`set()` accessors |

## Usage

```python
from partition.config.config_manager import ProjectConfigManager

config = ProjectConfigManager("config/project_config.yaml")
config.set_max_hop(5)
max_hop = config.get_max_hop()  # 5
```

## Key Features

- **YAML persistence** — Configuration survives pipeline restarts
- **Generic accessors** — `set(key, value)` / `get(key, default)` for arbitrary config
- **Max hop management** — `set_max_hop()` / `get_max_hop()` for graph traversal depth

## Dependencies

`PyYAML`, `structlog`
