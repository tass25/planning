# Prompt Library — Jinja2 Templates

> **Manager**: `PromptManager`  
> **Version**: 1.0.0  
> **Templates**: 6  

## Overview

Centralised prompt management using Jinja2 templates. All LLM prompts are
parameterised — no hard-coded strings in agent code. Templates are
version-controlled and auditable.

## Files

| File | Purpose |
|------|---------|
| `manager.py` | `PromptManager` — loads and renders `.j2` templates |
| `templates/translation_static.j2` | Static RAG translation prompt |
| `templates/translation_graph.j2` | GraphRAG translation prompt |
| `templates/translation_agentic.j2` | Agentic RAG translation prompt |
| `templates/cross_verify.j2` | Cross-verification prompt (Prompt C) |
| `templates/reflection.j2` | Self-reflection on failed validation |
| `templates/entity_extraction.j2` | Entity extraction for graph construction |

## Usage

```python
from partition.prompts import PromptManager

pm = PromptManager()
prompt = pm.render("translation_static", sas_code=code, similar_examples=examples)
```
