"""Merge layer (L4) — merge_script, consolidate_imports, NameRegistry, ReportAgent."""

from partition.merge.merge_agent import MergeAgent
from partition.merge.script_merger import merge_script
from partition.merge.import_consolidator import consolidate_imports
from partition.merge.dependency_injector import NameRegistry
from partition.merge.report_agent import ReportAgent

__all__ = [
    "MergeAgent",
    "merge_script",
    "consolidate_imports",
    "NameRegistry",
    "ReportAgent",
]
