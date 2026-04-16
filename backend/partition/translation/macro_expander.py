"""SAS %LET macro variable symbolic pre-processor.

Expands simple ``%LET var = value;`` definitions and substitutes ``&var``
references throughout the SAS code *before* the block reaches the LLM.

Why this matters
----------------
The LLM sees ``WHERE balance > &threshold`` as an opaque reference.
After expansion it sees ``WHERE balance > 5000`` — a concrete, translatable
condition. This eliminates a full category of translation errors for the
most common macro pattern in enterprise SAS.

What is expanded
----------------
* Literal numeric values:      ``%let n = 100;``
* Literal string values:       ``%let label = 'High Risk';``
* Simple arithmetic (eval):   ``%let x = %eval(5 + 3);`` → ``8``
* Indirect references:        ``&&x`` (double ampersand, expanded twice)
* ``%global`` / ``%local``    (same as %let for our purposes)

What is NOT expanded
--------------------
* Computed values: ``%let dt = %sysfunc(today(), date9.);``
* Macro function calls: ``%let x = %scan(...);``
* Multi-line macro definitions (%MACRO ... %MEND)
* Conditional macro logic (%IF/%THEN within macros)

These are left unexpanded (annotated in the expansion report) so the
LLM receives the original token and can apply heuristic translation.

Usage
-----
    from partition.translation.macro_expander import expand_macros

    expanded_code, report = expand_macros(sas_code)
    # inject report.to_prompt_block() into prompt if report.has_substitutions
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import structlog

logger = structlog.get_logger()

# SAS built-in macro functions we can evaluate trivially
_EVAL_PATTERN = re.compile(r"%eval\s*\(([^)]+)\)", re.IGNORECASE)
_SYSFUNC_PATTERN = re.compile(r"%sysfunc\s*\([^)]*\)", re.IGNORECASE)
_MACRO_CALL_PATTERN = re.compile(r"%\w+\s*\([^)]*\)", re.IGNORECASE)


@dataclass
class MacroExpansionReport:
    """Summary of what was expanded and what was left unexpanded."""
    substitutions: dict[str, str] = field(default_factory=dict)   # var → value
    unexpanded: list[str]         = field(default_factory=list)    # vars we couldn't resolve
    indirect_resolved: list[str]  = field(default_factory=list)    # &&var expansions
    eval_resolved: list[str]      = field(default_factory=list)    # %eval() expansions

    @property
    def has_substitutions(self) -> bool:
        return bool(self.substitutions or self.indirect_resolved)

    def to_prompt_block(self) -> str:
        """Render a ## Macro Variables block to inject into the LLM prompt."""
        if not (self.substitutions or self.unexpanded):
            return ""
        lines = ["## SAS Macro Variable Expansion"]
        if self.substitutions:
            lines.append("The following `%LET` variables were resolved and substituted:")
            for var, val in self.substitutions.items():
                lines.append(f"  - `&{var}` → `{val}`")
        if self.unexpanded:
            lines.append(
                "\nThe following macro references **could not be expanded** "
                "(dynamic / computed values) — translate them as Python variables:"
            )
            for var in self.unexpanded:
                lines.append(f"  - `&{var}` — define as a Python variable at the top of the script")
        return "\n".join(lines)


def _try_eval_arithmetic(expr: str) -> Optional[str]:
    """Attempt to evaluate simple integer arithmetic safely."""
    expr = expr.strip()
    if re.match(r"^[\d\s+\-*/()]+$", expr):
        try:
            result = eval(expr, {"__builtins__": {}})  # noqa: S307 — constrained to digits/ops
            return str(int(result))
        except Exception:
            pass
    return None


def _build_scope(sas_code: str) -> dict[str, str]:
    """Extract all %LET / %GLOBAL / %LOCAL definitions into a scope dict."""
    scope: dict[str, str] = {}

    # Pattern: %let varname = value; (value can be quoted or unquoted)
    let_pattern = re.compile(
        r"%(?:let|global|local)\s+(\w+)\s*=\s*"   # %let var =
        r"(['\"]?)([^;]*?)\2\s*;",                  # value (optionally quoted)
        re.IGNORECASE,
    )
    for m in let_pattern.finditer(sas_code):
        var   = m.group(1).lower()
        value = m.group(3).strip()

        # Try to resolve %eval() expressions
        eval_m = _EVAL_PATTERN.fullmatch(value.strip()) if value.strip() else None
        if eval_m:
            evaled = _try_eval_arithmetic(eval_m.group(1))
            if evaled is not None:
                scope[var] = evaled
                continue

        # Skip computed values (%sysfunc, %scan, other macro calls)
        if _SYSFUNC_PATTERN.search(value) or _MACRO_CALL_PATTERN.search(value):
            scope[var] = f"__UNEXPANDED__{value}"
            continue

        scope[var] = value

    return scope


def _substitute(code: str, scope: dict[str, str], report: MacroExpansionReport) -> str:
    """Substitute &var references, handling && indirect references."""

    # First pass: resolve &&var (double ampersand — one level of indirection)
    def resolve_indirect(m: re.Match) -> str:
        var = m.group(1).lower()
        if var in scope and not scope[var].startswith("__UNEXPANDED__"):
            # The value of &&var is &(value_of_var) — resolve once more
            resolved_name = scope[var].lower()
            if resolved_name in scope and not scope[resolved_name].startswith("__UNEXPANDED__"):
                report.indirect_resolved.append(f"&&{var} → &{resolved_name} → {scope[resolved_name]}")
                return scope[resolved_name]
        return m.group(0)

    code = re.sub(r"&&(\w+)", resolve_indirect, code, flags=re.IGNORECASE)

    # Second pass: resolve &var (single ampersand)
    def resolve_single(m: re.Match) -> str:
        # Skip %let definitions themselves
        var = m.group(1).lower()
        if var not in scope:
            report.unexpanded.append(var)
            return m.group(0)
        val = scope[var]
        if val.startswith("__UNEXPANDED__"):
            report.unexpanded.append(var)
            return m.group(0)
        report.substitutions[var] = val
        return val

    # Match &var but not inside %let ... ; definitions (avoid replacing the LHS)
    code = re.sub(r"&(\w+)", resolve_single, code, flags=re.IGNORECASE)

    return code


def _remove_let_statements(code: str) -> str:
    """Remove %LET / %GLOBAL / %LOCAL declarations (they've been resolved)."""
    return re.sub(
        r"%(?:let|global|local)\s+\w+\s*=[^;]*;",
        "",
        code,
        flags=re.IGNORECASE,
    ).strip()


def expand_macros(sas_code: str) -> tuple[str, MacroExpansionReport]:
    """Expand simple %LET macro variables in SAS code.

    Returns:
        (expanded_code, report) — expanded_code has &var references replaced
        with their literal values where possible.  The report summarises what
        was done so the caller can inject it into the LLM prompt.

    Side effects:
        Logs a warning for each unexpandable reference.
    """
    report = MacroExpansionReport()

    # Build scope from %LET definitions
    scope = _build_scope(sas_code)
    if not scope:
        return sas_code, report

    # Substitute references
    expanded = _substitute(sas_code, scope, report)

    # Remove %LET declarations that have been resolved (leave unexpandable ones)
    resolved_vars = {k for k, v in scope.items() if not v.startswith("__UNEXPANDED__")}
    if resolved_vars:
        expanded = re.sub(
            r"%(?:let|global|local)\s+(" + "|".join(re.escape(v) for v in resolved_vars) + r")\s*=[^;]*;",
            "",
            expanded,
            flags=re.IGNORECASE,
        )

    if report.unexpanded:
        logger.info(
            "macro_expansion_incomplete",
            unexpanded=list(set(report.unexpanded)),
            msg="Dynamic macro variables left unexpanded — LLM will handle",
        )

    if report.has_substitutions:
        logger.info(
            "macro_expansion_done",
            substituted=list(report.substitutions.keys()),
        )

    return expanded.strip(), report
