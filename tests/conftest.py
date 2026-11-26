import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "publish"))


@pytest.fixture
def fake_gopass(tmp_path, monkeypatch):
    """GopassStore wired to the fake gopass (no access to the real vault)."""
    from secrets_store import GopassStore
    monkeypatch.setenv("FAKE_GOPASS_DIR", str(tmp_path / "store"))
    store = GopassStore("coffre/test",
                        exe=[sys.executable, str(Path(__file__).with_name("fake_gopass.py"))])
    store.dir = tmp_path / "store"
    return store
