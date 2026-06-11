"""Tests for Session dataclass."""
import pytest
from webapp.backend.session import Session


def test_session_creation():
    """Session should be creatable with default values."""
    session = Session()
    assert session.viewport is None
    assert session.cell_selection == []
    assert session.h5cd_path is None
