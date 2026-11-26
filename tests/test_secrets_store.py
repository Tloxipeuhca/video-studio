"""Secret storage tests (no network, no real gopass)."""
import json

import pytest

from secrets_store import KEYS, FileStore, GopassStore, SecretError, make_store

TOKEN = {"access_token": "act.SECRET-VALUE-123", "refresh_token": "rft.SECRET-VALUE-456",
         "expires_at": "2026-11-27T10:00:00+00:00", "refresh_expires_at": "2027-11-26T10:00:00+00:00"}


# ------------------------------------------------------------------ fichiers
def test_files_roundtrip(tmp_path):
    st = FileStore(tmp_path)
    assert st.get("tiktok.token.json") is None
    st.put("tiktok.token.json", TOKEN)
    assert st.get("tiktok.token.json") == TOKEN


def test_files_client_secret_glob(tmp_path):
    (tmp_path / "client_secret_123.apps.googleusercontent.com.json").write_text('{"installed": {"client_id": "x"}}')
    assert FileStore(tmp_path).get("youtube.client_secret.json") == {"installed": {"client_id": "x"}}


# -------------------------------------------------------------------- gopass
def test_gopass_roundtrip(fake_gopass):
    fake_gopass.put("tiktok.token.json", TOKEN)
    assert fake_gopass.get("tiktok.token.json") == TOKEN


def test_gopass_keys_under_prefix(fake_gopass):
    assert fake_gopass.key("youtube.token.json") == "coffre/test/youtube/token"
    assert set(KEYS) == {"youtube.client_secret.json", "youtube.token.json", "tiktok_app.json", "tiktok.token.json"}


def test_gopass_missing_is_none(fake_gopass):
    assert fake_gopass.get("tiktok.token.json") is None


def test_gopass_read_does_not_overwrite(fake_gopass):
    """Critical point: a read must never be taken for a write (stdin = /dev/null)."""
    fake_gopass.put("tiktok_app.json", {"client_key": "k", "client_secret": "s"})
    for _ in range(3):
        assert fake_gopass.get("tiktok_app.json") == {"client_key": "k", "client_secret": "s"}


def test_gopass_secret_never_in_argv(fake_gopass):
    fake_gopass.put("tiktok.token.json", TOKEN)
    fake_gopass.get("tiktok.token.json")
    argv_log = (fake_gopass.dir / "_argv.log").read_text(encoding="utf-8")
    assert "SECRET-VALUE" not in argv_log
    assert "cat coffre/test/tiktok/token" in argv_log


def test_gopass_unicode(fake_gopass):
    fake_gopass.put("tiktok_app.json", {"client_key": "key-é", "client_secret": "🔑"})
    assert fake_gopass.get("tiktok_app.json")["client_secret"] == "🔑"


def test_gopass_non_json_raises(fake_gopass):
    fake_gopass.put_raw(fake_gopass.key("tiktok_app.json"), "not json")
    with pytest.raises(SecretError, match="not JSON"):
        fake_gopass.get("tiktok_app.json")


def test_gopass_unknown_name(fake_gopass):
    with pytest.raises(SecretError, match="Unknown"):
        fake_gopass.get("autre.json")


def test_gopass_compact_single_line(fake_gopass):
    fake_gopass.put("tiktok.token.json", TOKEN)
    raw = (fake_gopass.dir / "coffre__test__tiktok__token").read_text(encoding="utf-8")
    assert "\n" not in raw and json.loads(raw) == TOKEN


def test_gopass_error_message_has_no_value(tmp_path, monkeypatch):
    st = GopassStore("p", exe=["false"])  # command that always fails
    with pytest.raises(SecretError) as e:
        st.put("tiktok.token.json", TOKEN)
    assert "SECRET-VALUE" not in str(e.value)


# --------------------------------------------------------------- configuration
def test_make_store_default_files(tmp_path):
    assert isinstance(make_store(tmp_path, {}.get), FileStore)


def test_make_store_gopass(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/gopass")
    st = make_store(tmp_path, {"VS_SECRETS_BACKEND": "gopass", "VS_GOPASS_PREFIX": "coffre/x/"}.get)
    assert isinstance(st, GopassStore) and st.prefix == "coffre/x" and st.exe == ["/usr/bin/gopass"]


def test_make_store_gopass_wrapper(tmp_path):
    cfg = {"VS_SECRETS_BACKEND": "gopass", "VS_GOPASS_CMD": "bash /opt/wrapper.sh gopass"}
    st = make_store(tmp_path, cfg.get)
    assert st.exe == ["bash", "/opt/wrapper.sh", "gopass"] and st.prefix == "video-studio"


def test_make_store_unknown(tmp_path):
    with pytest.raises(SecretError):
        make_store(tmp_path, {"VS_SECRETS_BACKEND": "keepass"}.get)
