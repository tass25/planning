"""Compile CDAIS + MIS modules to native C extensions via Cython.

Runs during Docker build (Stage 2) to protect IP before shipping.
The resulting .so binaries are practically impossible to reverse-engineer.
"""
from __future__ import annotations

from Cython.Build import cythonize
from setuptools import setup

PROTECTED_MODULES = [
    "partition/testing/cdais/cdais_runner.py",
    "partition/testing/cdais/constraint_catalog.py",
    "partition/testing/cdais/coverage_oracle.py",
    "partition/testing/cdais/synthesizer.py",
    "partition/invariant/invariant_synthesizer.py",
]

setup(
    ext_modules=cythonize(PROTECTED_MODULES, language_level="3"),
    script_args=["build_ext", "--inplace"],
)
