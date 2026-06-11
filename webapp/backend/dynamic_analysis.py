"""Sandbox for agent-authored analysis functions.

Phase 1 MVP security model (see context/.../dynamic_codegen_implementation_plan.md):

1. AST allowlist — reject dangerous node types (import, global, with, async,
   lambda) and dangerous names (eval/exec/open/getattr/...) BEFORE compile.
2. Block ALL dunder attribute access — kills the classic
   ``().__class__.__bases__[0].__subclasses__()`` escape chain.
3. Replace ``__builtins__`` with a tiny safe allowlist (no __import__, no open,
   no getattr) so even if the AST check misses something, the name resolves to
   nothing dangerous at runtime.
4. Pre-bind only ``np`` / ``pd`` so the agent never needs ``import``.

Execution timeout uses ``concurrent.futures.ThreadPoolExecutor`` — NOT
``signal.alarm`` — because REST endpoints run in FastAPI's threadpool (not the
main thread) where ``signal.signal`` raises ValueError.
"""
from __future__ import annotations

import ast
import builtins as _builtins
import threading
from dataclasses import dataclass
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd


class AnalysisValidationError(Exception):
    """Raised when agent-authored source fails the sandbox allowlist."""


# ---------------------------------------------------------------------------
# Allow / deny lists
# ---------------------------------------------------------------------------

# Node types that are never allowed anywhere in the source tree.
FORBIDDEN_NODES = (
    ast.Import, ast.ImportFrom,          # no import — np/pd are pre-bound
    ast.Global, ast.Nonlocal,            # no scope escape
    ast.With, ast.AsyncWith,             # no context managers (open, locks)
    ast.AsyncFunctionDef, ast.Await,     # no async
    ast.Lambda,                          # keep the tree statically analysable
)

# Names that must never appear (as a Name load, attribute, or call target).
FORBIDDEN_NAMES = frozenset({
    "eval", "exec", "compile", "open", "input", "__import__",
    "globals", "locals", "vars", "dir",
    "getattr", "setattr", "delattr", "hasattr",
    "breakpoint", "memoryview", "classmethod", "staticmethod",
    "super", "type", "object", "property", "exit", "quit",
    "help", "copyright", "credits", "license",
})

# Any attribute containing a dunder is rejected (closes the escape chain via
# __class__ / __globals__ / __subclasses__ / __builtins__ / ...).
FORBIDDEN_ATTR_SUBSTR = ("__",)

# The ONLY builtins exposed to the sandboxed function. Deliberately no
# __import__, no open, no getattr, no type/object.
_SAFE_BUILTIN_NAMES = (
    "len", "range", "enumerate", "zip", "min", "max", "sum",
    "abs", "round", "sorted", "reversed",
    "list", "dict", "set", "tuple", "frozenset",
    "float", "int", "str", "bool", "complex",
    "map", "filter", "any", "all",
    "isinstance", "divmod", "pow",
)
SAFE_BUILTINS: dict[str, Any] = {
    name: getattr(_builtins, name)
    for name in _SAFE_BUILTIN_NAMES
    if hasattr(_builtins, name)
}

# Modules pre-bound into the sandbox namespace (no import needed).
ALLOWED_MODULES: dict[str, Any] = {"np": np, "pd": pd}

# Mandatory entry-point function name.
REQUIRED_FUNCTION = "analyze"


# ---------------------------------------------------------------------------
# AST validation
# ---------------------------------------------------------------------------

class _Validator(ast.NodeVisitor):
    def __init__(self) -> None:
        self.errors: list[str] = []

    def visit(self, node: ast.AST) -> None:
        if isinstance(node, FORBIDDEN_NODES):
            self.errors.append(
                f"Forbidden syntax: {type(node).__name__} is not allowed "
                f"(no import/global/with/async/lambda)."
            )
            # Don't descend further into a forbidden node.
            return
        super().visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in FORBIDDEN_NAMES:
            self.errors.append(f"Forbidden name: '{node.id}'.")
        if any(s in node.id for s in FORBIDDEN_ATTR_SUBSTR):
            self.errors.append(f"Forbidden dunder name: '{node.id}'.")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if any(s in node.attr for s in FORBIDDEN_ATTR_SUBSTR):
            self.errors.append(
                f"Forbidden dunder attribute access: '.{node.attr}'."
            )
        if node.attr in FORBIDDEN_NAMES:
            self.errors.append(f"Forbidden attribute: '.{node.attr}'.")
        self.generic_visit(node)


def validate_source(source: str) -> ast.Module:
    """Parse + allowlist-check the source. Returns the AST on success.

    Raises AnalysisValidationError on any syntax error or policy violation,
    or if a top-level ``def analyze(...)`` is not defined.
    """
    if not source or not source.strip():
        raise AnalysisValidationError("Empty source.")

    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as e:
        raise AnalysisValidationError(f"Syntax error: {e}") from e

    validator = _Validator()
    validator.visit(tree)
    if validator.errors:
        raise AnalysisValidationError("; ".join(dict.fromkeys(validator.errors)))

    # Require a top-level function named `analyze`.
    func_defs = [
        n for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == REQUIRED_FUNCTION
    ]
    if not func_defs:
        raise AnalysisValidationError(
            f"Source must define a top-level function '{REQUIRED_FUNCTION}"
            "(cd, chrom, **params)'."
        )

    return tree


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------

@dataclass
class CompiledAnalysis:
    name: str
    source: str
    fn: Callable[..., pd.DataFrame]
    chromosome_field: str = "chrom"
    genomic_fields: tuple = ("start", "end")
    suggested_mark: str = "rule"
    result_key: str = "records"


def compile_analysis(name: str, source: str, **meta: Any) -> CompiledAnalysis:
    """Validate + compile + bind source into a restricted namespace.

    `meta` may carry chromosome_field / genomic_fields / suggested_mark /
    result_key overrides (forwarded to the CompiledAnalysis dataclass).
    """
    tree = validate_source(source)
    code = compile(tree, filename=f"<analysis:{name}>", mode="exec")

    sandbox_globals: dict[str, Any] = {
        "__builtins__": SAFE_BUILTINS,
        **ALLOWED_MODULES,
    }
    sandbox_locals: dict[str, Any] = {}
    try:
        exec(code, sandbox_globals, sandbox_locals)
    except Exception as e:  # pragma: no cover - defensive
        raise AnalysisValidationError(f"Failed to compile source: {e}") from e

    fn = sandbox_locals.get(REQUIRED_FUNCTION)
    if not callable(fn):
        raise AnalysisValidationError(
            f"'{REQUIRED_FUNCTION}' is not defined as a function."
        )

    genomic_fields = meta.get("genomic_fields", ("start", "end"))
    if isinstance(genomic_fields, list):
        genomic_fields = tuple(genomic_fields)

    return CompiledAnalysis(
        name=name,
        source=source,
        fn=fn,
        chromosome_field=meta.get("chromosome_field", "chrom"),
        genomic_fields=genomic_fields,
        suggested_mark=meta.get("suggested_mark", "rule"),
        result_key=meta.get("result_key", "records"),
    )


# ---------------------------------------------------------------------------
# Timed execution
# ---------------------------------------------------------------------------

def run_with_timeout(
    compiled: CompiledAnalysis,
    cd: Any,
    chrom: str,
    params: Optional[dict] = None,
    timeout_s: float = 10.0,
) -> pd.DataFrame:
    """Run compiled.fn(cd, chrom, **params) with a wall-clock timeout.

    Uses a daemon thread (NOT signal.alarm — REST endpoints run off the main
    thread). A timed-out thread cannot be hard-killed in Phase 1, but being a
    daemon it never blocks interpreter exit (plan §7; Phase 2 swaps in a
    ProcessPool for true kill).

    Raises:
        TimeoutError: if execution exceeds timeout_s.
        TypeError: if the function does not return a pandas DataFrame.
        Exception: any error raised inside the analysis function propagates.
    """
    box: dict[str, Any] = {}

    def _target():
        try:
            box["result"] = compiled.fn(cd, chrom, **(params or {}))
        except BaseException as e:  # noqa: BLE001 - re-raised on the caller side
            box["error"] = e

    worker = threading.Thread(
        target=_target, name=f"dyn-analysis-{compiled.name}", daemon=True
    )
    worker.start()
    worker.join(timeout=timeout_s)

    if worker.is_alive():
        raise TimeoutError(
            f"analysis '{compiled.name}' exceeded {timeout_s:.0f}s timeout"
        )
    if "error" in box:
        raise box["error"]

    result = box.get("result")
    if not isinstance(result, pd.DataFrame):
        raise TypeError(
            f"analyze() must return a pandas DataFrame, got "
            f"{type(result).__name__}."
        )
    return result
