import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bulk_toys import toy_population  # noqa: E402


@pytest.fixture
def toy():
    return toy_population()
