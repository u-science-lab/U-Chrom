"""Tests for notebook_api kernel management."""
import pytest
from webapp.backend.notebook_api import start_kernel, execute_code, stop_kernel


@pytest.fixture
def kernel():
    """Start kernel for tests, stop after."""
    start_kernel()
    yield
    stop_kernel()


def test_execute_simple_code(kernel):
    """Execute simple Python code."""
    result = execute_code("1 + 1")
    assert result["status"] == "ok"
    assert "2" in result["output"]


def test_execute_with_error(kernel):
    """Execute code that raises error."""
    result = execute_code("raise ValueError('test')")
    assert result["status"] == "error"
    assert "ValueError" in result["error"]


def test_execute_multiple_outputs(kernel):
    """Execute code with multiple print statements."""
    result = execute_code("print('a')\nprint('b')")
    assert result["status"] == "ok"
    assert "a" in result["output"]
    assert "b" in result["output"]
