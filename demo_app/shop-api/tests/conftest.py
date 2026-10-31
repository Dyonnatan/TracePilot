import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("OTEL_SDK_DISABLED", "true")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import faults  # noqa: E402


@pytest.fixture(autouse=True)
def reset_fault_flags():
    yield
    for name in faults.KNOWN_FLAGS:
        faults.registry.set(name, False)
