"""Storage for publishing secrets: gopass (recommended) or plain files in secrets/ (legacy).

The backend is chosen with VS_* settings (environment, otherwise the .env file — see settings.py
and docs/configuration.md):
  VS_SECRETS_BACKEND  gopass | files (default: files, folder secrets/)
  VS_GOPASS_PREFIX    entry prefix, e.g. "vault-low/video-studio"
  VS_GOPASS_CMD       command used instead of "gopass" (e.g. a wrapper selecting the vault profile)

With gopass, each secret is a compact JSON document stored with "gopass cat":
  - read : gopass cat <key>  with stdin = /dev/null (otherwise gopass assumes a write)
  - write: gopass cat <key>  with the JSON on stdin (never on the command line)
Nothing is written to disk in clear text.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

# Logical name (historically the file name in secrets/) -> gopass key under the prefix
KEYS = {
    "youtube.client_secret.json": "youtube/client_secret",
    "youtube.token.json": "youtube/token",
    "tiktok_app.json": "tiktok/app",
    "tiktok.token.json": "tiktok/token",
}
DEFAULT_PREFIX = "video-studio"
NOT_FOUND_HINTS = ("not in the password store", "not found", "does not exist", "no such",
                   "entry is not", "failed to retrieve")


class SecretError(Exception):
    """Secret storage error (the message never contains a secret value)."""


class FileStore:
    """Legacy mode: one JSON file per secret in secrets/."""
    kind = "files"

    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, name: str) -> Path:
        if name == "youtube.client_secret.json":  # file name as downloaded from Google Cloud
            files = sorted(self.root.glob("client_secret*.json"),
                           key=lambda f: f.stat().st_mtime, reverse=True)
            if files:
                return files[0]
        return self.root / name

    def get(self, name: str):
        path = self._path(name)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def put(self, name: str, data) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def describe(self) -> str:
        return f"files ({self.root})"


class GopassStore:
    """Secrets in gopass, under a prefix (vault mount + project folder)."""
    kind = "gopass"

    def __init__(self, prefix: str = DEFAULT_PREFIX, exe=None, timeout: int = 60):
        self.prefix = prefix.strip("/")
        if exe is None:
            found = shutil.which("gopass")
            if not found:
                raise SecretError("gopass not found in PATH.")
            exe = [found]
        self.exe = [exe] if isinstance(exe, (str, Path)) else list(exe)
        self.timeout = timeout

    def key(self, name: str) -> str:
        if name not in KEYS:
            raise SecretError(f"Unknown secret: {name}")
        return f"{self.prefix}/{KEYS[name]}"

    def _run(self, args: list[str], payload: bytes | None = None):
        try:
            return subprocess.run(self.exe + args, capture_output=True, timeout=self.timeout,
                                  input=payload,
                                  stdin=subprocess.DEVNULL if payload is None else None)
        except subprocess.TimeoutExpired:
            raise SecretError(f"gopass {args[0]}: timed out after {self.timeout} s. "
                              "Vault locked, or waiting for a passphrase?") from None

    def get_raw(self, key: str):
        r = self._run(["cat", key])
        if r.returncode != 0:
            err = r.stderr.decode("utf-8", "replace").strip()
            if any(h in err.lower() for h in NOT_FOUND_HINTS):
                return None
            raise SecretError(f"gopass cat {key}: {err or f'exit code {r.returncode}'}")
        return r.stdout.decode("utf-8")

    def put_raw(self, key: str, text: str) -> None:
        r = self._run(["cat", key], payload=text.encode("utf-8"))
        if r.returncode != 0:
            err = r.stderr.decode("utf-8", "replace").strip()
            raise SecretError(f"Cannot write gopass entry {key}: {err or f'exit code {r.returncode}'}")

    def remove_raw(self, key: str) -> None:
        self._run(["rm", "-f", key])

    def get(self, name: str):
        key = self.key(name)
        text = self.get_raw(key)
        if text is None or not text.strip():
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise SecretError(f"{key}: content is not JSON ({e.msg}, line {e.lineno}).") from None

    def put(self, name: str, data) -> None:
        self.put_raw(self.key(name), json.dumps(data, ensure_ascii=False, separators=(",", ":")))

    def describe(self) -> str:
        return f"gopass ({self.prefix})"


def make_store(root: Path, get=None):
    """Builds the store from the configuration. get(name) -> value; settings.get by default."""
    if get is None:
        from settings import get
    backend = (get("VS_SECRETS_BACKEND") or "files").lower()
    if backend == "gopass":
        command = (get("VS_GOPASS_CMD") or "").split() or None
        return GopassStore(get("VS_GOPASS_PREFIX") or DEFAULT_PREFIX, exe=command)
    if backend == "files":
        return FileStore(Path(root) / "secrets")
    raise SecretError(f"Unknown VS_SECRETS_BACKEND: {backend!r} (expected gopass or files)")
