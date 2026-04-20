"""DependencyInjector — Merge Layer (L4)

Resolves variable name consistency across translated partitions.
Builds a name_registry mapping SAS dataset names → Python variable names.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog

log = structlog.get_logger(__name__)

SAS_DATASET_PATTERN = re.compile(
    r"\b(?:DATA\s+|SET\s+|MERGE\s+)([\w.]+)",
    re.IGNORECASE,
)


def sas_name_to_snake(sas_name: str) -> str:
    """Convert SAS dataset name to Python snake_case.

    WORK.TEMP_CUSTOMERS → work_temp_customers
    SASDATA.SALES_2024  → sasdata_sales_2024
    """
    return sas_name.replace(".", "_").lower()


@dataclass
class NameRegistry:
    """Registry of SAS dataset → Python variable name mappings."""

    _names: dict[str, str] = field(default_factory=dict)
    _producers: dict[str, str] = field(default_factory=dict)

    def register(self, sas_name: str, source_file_id: str) -> str:
        python_name = sas_name_to_snake(sas_name)
        self._names[sas_name.upper()] = python_name
        self._producers[python_name] = source_file_id
        return python_name

    def lookup(self, sas_name: str) -> str | None:
        return self._names.get(sas_name.upper())

    def get_producer(self, python_name: str) -> str | None:
        return self._producers.get(python_name)


def build_name_registry(
    partitions: list[dict],
    source_file_id: str,
) -> NameRegistry:
    """Scan all partitions' source code to build a NameRegistry."""
    registry = NameRegistry()
    for partition in partitions:
        raw_code = partition.get("raw_code", partition.get("source_code", ""))
        matches = SAS_DATASET_PATTERN.findall(raw_code)
        for sas_name in matches:
            registry.register(sas_name.strip(), source_file_id)
    return registry


def inject_variable_names(
    python_code: str,
    registry: NameRegistry,
    source_file_id: str,
) -> str:
    """Patch python_code to use consistent variable names from the registry."""
    patched = python_code
    for sas_name, python_name in registry._names.items():
        sas_variants = [
            sas_name,
            sas_name.lower(),
            sas_name.replace(".", "_"),
        ]
        for variant in sas_variants:
            if variant in patched and variant != python_name:
                patched = patched.replace(variant, python_name)
    return patched


def add_cross_file_stubs(
    python_code: str,
    unresolved_refs: list[str],
    source_files: dict[str, str],
) -> str:
    """Insert # NOTE stubs for unresolvable cross-file references."""
    if not unresolved_refs:
        return python_code
    stubs = []
    for ref in unresolved_refs:
        source = source_files.get(ref, "unknown")
        stubs.append(f"# NOTE: '{ref}' expected from external file '{source}'")
    stub_block = "\n".join(stubs) + "\n\n"
    return stub_block + python_code
