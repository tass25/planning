"""namespace_checker.py — AST-level namespace safety checker for merged Python.

Catches two categories of bugs that ImportConsolidator + DependencyInjector
cannot detect (they work on text, not semantics):

  1. USE_BEFORE_DEF  : a variable is Read before any assignment defines it.
                       Indicates wrong chunk ordering in the DAG or a
                       translator that forgot to initialise an accumulator.

  2. SHADOW_CONFLICT : a loop variable or inner assignment shadows a
                       DataFrame name from a prior chunk, which can silently
                       corrupt downstream reads.

Usage::

    from partition.merge.namespace_checker import NamespaceCheckResult, check_namespace

    result = check_namespace(merged_python_code)
    if result.has_errors:
        for err in result.errors:
            print(err)           # e.g. "Line 42: CRITICAL — 'total' read before defined"
    if result.has_warnings:
        for w in result.warnings:
            print(w)
"""

from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass, field

# Names that are always defined — builtins + common library aliases injected
# by the pipeline merge step.
_PRELOADED: frozenset[str] = frozenset(dir(builtins)) | frozenset(
    {
        "pd",
        "np",
        "plt",
        "sns",
        "spark",
        "F",
        "Window",
        "os",
        "sys",
        "re",
        "json",
        "math",
        "datetime",
        "Path",
        "io",
        "itertools",
        "collections",
        "functools",
        # pandas/numpy types that appear as names
        "DataFrame",
        "Series",
        "Index",
        "NaN",
        "inf",
        # common pipeline injections
        "df",
        "df_in",
        "df_out",
    }
)


@dataclass
class NamespaceViolation:
    line: int
    kind: str  # "USE_BEFORE_DEF" | "SHADOW_CONFLICT"
    name: str
    message: str

    def __str__(self) -> str:
        return f"Line {self.line}: [{self.kind}] '{self.name}' — {self.message}"


@dataclass
class NamespaceCheckResult:
    errors: list[NamespaceViolation] = field(default_factory=list)
    warnings: list[NamespaceViolation] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)

    def to_report_block(self) -> str:
        if not self.errors and not self.warnings:
            return ""
        lines = ["## Namespace Check Results"]
        if self.errors:
            lines.append(f"\n**{len(self.errors)} error(s)**:")
            lines.extend(f"  - {e}" for e in self.errors)
        if self.warnings:
            lines.append(f"\n**{len(self.warnings)} warning(s)**:")
            lines.extend(f"  - {w}" for w in self.warnings)
        return "\n".join(lines)


# ── AST visitor ───────────────────────────────────────────────────────────────


class _NamespaceVisitor(ast.NodeVisitor):
    """Walk a merged Python AST top-to-bottom, tracking definitions.

    Rules:
      - An ast.Name in Load context that is not in `defined` → USE_BEFORE_DEF error.
      - A For/With target that matches a name already defined as a DataFrame
        literal (i.e., assigned via pd.DataFrame / pd.read_*) → SHADOW_CONFLICT warning.
    """

    def __init__(self) -> None:
        self.defined: set[str] = set(_PRELOADED)
        self.df_names: set[str] = set()  # names known to hold DataFrames
        self.errors: list[NamespaceViolation] = []
        self.warnings: list[NamespaceViolation] = []

    # ── helpers ────────────────────────────────────────────────────────────────

    def _define(self, name: str) -> None:
        self.defined.add(name)

    def _define_target(self, node: ast.expr) -> None:
        """Recursively register all names in an assignment target."""
        if isinstance(node, ast.Name):
            self._define(node.id)
        elif isinstance(node, (ast.Tuple, ast.List)):
            for elt in node.elts:
                self._define_target(elt)
        elif isinstance(node, ast.Starred):
            self._define_target(node.value)

    def _is_df_expr(self, node: ast.expr) -> bool:
        """Heuristic: does this expression produce a DataFrame?"""
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if func.attr in {
                    "DataFrame",
                    "read_csv",
                    "read_excel",
                    "read_parquet",
                    "read_sas",
                    "merge",
                    "concat",
                    "groupby",
                    "reset_index",
                    "sort_values",
                    "drop_duplicates",
                    "rename",
                    "assign",
                    "pivot_table",
                    "pivot",
                    "melt",
                    "explode",
                    "fillna",
                    "dropna",
                    "copy",
                }:
                    return True
        if isinstance(node, ast.Name) and node.id in self.df_names:
            return True
        return False

    # ── visitors ───────────────────────────────────────────────────────────────

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._define(alias.asname or alias.name.split(".")[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self._define(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # Check RHS for undefined names FIRST
        self.visit(node.value)
        # Then register LHS names and detect DataFrame assignments
        for target in node.targets:
            if isinstance(target, ast.Name):
                if self._is_df_expr(node.value):
                    self.df_names.add(target.id)
            self._define_target(target)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value:
            self.visit(node.value)
        if isinstance(node.target, ast.Name):
            self._define_target(node.target)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        # x += expr  — x must already be defined
        if isinstance(node.target, ast.Name):
            if node.target.id not in self.defined:
                self.errors.append(
                    NamespaceViolation(
                        line=node.lineno,
                        kind="USE_BEFORE_DEF",
                        name=node.target.id,
                        message=(
                            f"augmented assignment `{node.target.id} +=` but "
                            f"`{node.target.id}` was not defined above this line."
                        ),
                    )
                )
        self.visit(node.value)
        self._define_target(node.target)

    def visit_For(self, node: ast.For) -> None:
        # Check iterable first
        self.visit(node.iter)
        # Register loop variable — warn if it shadows a DataFrame
        if isinstance(node.target, ast.Name):
            if node.target.id in self.df_names:
                self.warnings.append(
                    NamespaceViolation(
                        line=node.lineno,
                        kind="SHADOW_CONFLICT",
                        name=node.target.id,
                        message=(
                            f"loop variable `{node.target.id}` shadows a DataFrame "
                            "from a prior chunk — downstream code reading this name "
                            "will get a loop scalar, not the DataFrame."
                        ),
                    )
                )
            self._define_target(node.target)
        for stmt in node.body:
            self.visit(stmt)
        for stmt in node.orelse:
            self.visit(stmt)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars:
                self._define_target(item.optional_vars)
        for stmt in node.body:
            self.visit(stmt)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # Register the function name; do NOT enter body (inner scope is independent)
        self._define(node.name)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._define(node.name)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            if node.id not in self.defined:
                self.errors.append(
                    NamespaceViolation(
                        line=node.lineno,
                        kind="USE_BEFORE_DEF",
                        name=node.id,
                        message=(
                            f"`{node.id}` is read before it is defined. "
                            "Check chunk ordering in the dependency graph."
                        ),
                    )
                )
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> None:
        for name in node.names:
            self._define(name)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        for name in node.names:
            self._define(name)

    # Handle comprehension scopes (they define their own loop var)
    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comprehension(node.generators, node.elt)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comprehension(node.generators, node.elt)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comprehension(node.generators, node.elt)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comprehension(node.generators, node.key, node.value)

    def _visit_comprehension(
        self,
        generators: list[ast.comprehension],
        *bodies: ast.expr,
    ) -> None:
        inner = set(self.defined)  # snapshot — comprehension has own scope
        for gen in generators:
            # iter is evaluated in outer scope
            self.visit(gen.iter)
            # target defined in inner scope
            if isinstance(gen.target, ast.Name):
                inner.add(gen.target.id)
            for cond in gen.ifs:
                # conditions evaluated in inner scope — use generic_visit
                pass
        # bodies evaluated in inner scope — skip (no mutation of outer defined)


# ── public API ────────────────────────────────────────────────────────────────


def check_namespace(python_code: str) -> NamespaceCheckResult:
    """Parse and walk the merged Python code, returning namespace violations.

    Args:
        python_code: The fully merged Python script (after ImportConsolidator
                     and DependencyInjector have run).

    Returns:
        NamespaceCheckResult with .errors and .warnings lists.
        Returns an empty result (no violations) when the code cannot be parsed
        (syntax errors are ValidationAgent's job, not ours).
    """
    result = NamespaceCheckResult()
    if not python_code or not python_code.strip():
        return result
    try:
        tree = ast.parse(python_code)
    except SyntaxError:
        return result  # syntax errors handled by ValidationAgent

    visitor = _NamespaceVisitor()
    visitor.visit(tree)
    result.errors = visitor.errors
    result.warnings = visitor.warnings
    return result
