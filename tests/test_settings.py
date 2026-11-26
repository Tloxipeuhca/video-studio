"""Tests for reading .env (settings.py)."""
import settings


def test_parse_env():
    text = """
# comment
VS_SERVER=user@10.0.0.1
VS_SERVER_DIR = /srv/video-studio
VS_GOPASS_CMD="bash /opt/w.sh gopass"
VS_CHROME_PATH=C:\\Program Files\\Chrome\\chrome.exe
VS_CHROME_PROFILE='Profile 2'
export VS_X=1   # end of line
EMPTY=
line without equals sign
"""
    v = settings.parse_env(text)
    assert v["VS_SERVER"] == "user@10.0.0.1"
    assert v["VS_SERVER_DIR"] == "/srv/video-studio"
    assert v["VS_GOPASS_CMD"] == "bash /opt/w.sh gopass"
    assert v["VS_CHROME_PATH"] == "C:\\Program Files\\Chrome\\chrome.exe"
    assert v["VS_CHROME_PROFILE"] == "Profile 2"
    assert v["VS_X"] == "1"
    assert v["EMPTY"] == ""


def test_env_var_overrides_file(monkeypatch):
    monkeypatch.setattr(settings, "_values", {"VS_SERVER": "fichier"})
    assert settings.get("VS_SERVER") == "fichier"
    monkeypatch.setenv("VS_SERVER", "environnement")
    assert settings.get("VS_SERVER") == "environnement"


def test_default_when_missing_or_empty(monkeypatch):
    monkeypatch.setattr(settings, "_values", {"EMPTY": ""})
    monkeypatch.delenv("EMPTY", raising=False)
    assert settings.get("EMPTY", "default") == "default"
    assert settings.get("ABSENT") is None


def test_example_file_is_complete():
    """Every setting read by the code is documented in .env.example."""
    example = settings.parse_env((settings.ROOT / ".env.example").read_text(encoding="utf-8"))
    for name in ("VS_SERVER", "VS_SERVER_DIR", "VS_SECRETS_BACKEND", "VS_GOPASS_PREFIX",
                 "VS_GOPASS_CMD", "VS_CHROME_PATH", "VS_CHROME_PROFILE", "VS_TIKTOK_SCOPES"):
        assert name in example, name
