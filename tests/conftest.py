"""Shared pytest configuration for the test suite.

Guarantees the repository root is on ``sys.path`` so tests can import both the
application package (``webapp.backend...``) and sibling test helpers
(``from tests._agent_loop_harness import ...``) regardless of how pytest is
invoked (``pytest`` console script vs ``python -m pytest``) or from which
working directory. conftest.py is auto-loaded by pytest before any test module
is imported, so the path is in place before collection.
"""
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
