import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path, monkeypatch):
    """Keep paper files, discovery state, and locks out of the real desk directory."""
    monkeypatch.chdir(tmp_path)
    return tmp_path
