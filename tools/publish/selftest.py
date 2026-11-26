"""Self-test of the publishing machine (run on the Linux server, .venv activated).

    python tools/publish/selftest.py            # local checks, no network
    python tools/publish/selftest.py --online   # + read-only calls to YouTube and TikTok

Never prints a secret value: only its presence, its fields and its expiry dates.
Exit code 0 when everything is OK, 1 otherwise.
"""
from __future__ import annotations

import argparse
import os
import secrets as pysecrets
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from common import ROOT, PublishError, load_secret, secret_store
from secrets_store import KEYS, GopassStore, SecretError

REQUIRED = {  # logical name -> expected fields
    "youtube.client_secret.json": ["installed"],
    "youtube.token.json": ["refresh_token", "client_id", "client_secret", "scopes"],
    "tiktok_app.json": ["client_key", "client_secret"],
    "tiktok.token.json": ["access_token", "refresh_token", "expires_at", "refresh_expires_at"],
}
results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    results.append((ok, label))
    print(f"  [{'OK' if ok else 'KO'}] {label}" + (f" — {detail}" if detail else ""), flush=True)
    return ok


def section(title: str) -> None:
    print(f"\n== {title}", flush=True)


def tools() -> None:
    section("Tools")
    for exe in ("ffmpeg", "ffprobe"):
        check(bool(shutil.which(exe)), f"{exe} in PATH", shutil.which(exe) or "missing")
    tz = datetime.now().astimezone().tzname()
    check(True, "local time zone", f"{tz} (\"schedule\" dates without a time zone are read in this one)")


def config() -> None:
    section("Configuration")
    from settings import ENV_FILE, get
    check(ENV_FILE.exists(), ".env present", str(ENV_FILE) if ENV_FILE.exists() else "copy .env.example to .env")
    for name in ("VS_SECRETS_BACKEND", "VS_GOPASS_PREFIX", "VS_GOPASS_CMD", "VS_TIKTOK_SCOPES"):
        check(True, name, get(name) or "(not set, default value)")


def store() -> None:
    section("Secret storage")
    try:
        st = secret_store()
    except PublishError as e:
        check(False, "configuration", str(e))
        return
    check(True, "storage", st.describe())
    if not isinstance(st, GopassStore):
        check(sys.platform == "win32", "gopass expected on the Linux server",
              ".env: VS_SECRETS_BACKEND=gopass (see docs/configuration.md)")
        return
    ver = subprocess.run(st.exe + ["version"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    out = (ver.stdout or ver.stderr).strip()
    check(ver.returncode == 0, "gopass answers", out.splitlines()[0] if out else "")
    mounts = subprocess.run(st.exe + ["mounts"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    mount = st.prefix.split("/")[0]
    check(mount in mounts.stdout, f"mount \"{mount}\" present", "see \"gopass mounts\"")

    probe = f"{st.prefix}/_selftest/probe"
    value = pysecrets.token_hex(16)
    try:
        st.put_raw(probe, value)
        first, second = st.get_raw(probe), st.get_raw(probe)
        check((first or "").strip() == value, "write then read (gopass cat)")
        check((second or "").strip() == value, "a read does not modify the entry")
    except SecretError as e:
        check(False, "write/read", str(e))
    finally:
        st.remove_raw(probe)


def secrets_present() -> None:
    section("Project secrets")
    for name, fields in REQUIRED.items():
        where = KEYS[name]
        try:
            data = load_secret(name, required=False)
        except PublishError as e:
            check(False, where, str(e))
            continue
        if data is None:
            check(False, where, "missing")
            continue
        root = data.get("installed", data) if name == "youtube.client_secret.json" else data
        missing = [f for f in fields if f not in data and f not in root]
        check(not missing, where, "missing fields: " + ", ".join(missing) if missing else "present")
        if name == "tiktok.token.json" and not missing:
            now = datetime.now(timezone.utc)
            for f in ("expires_at", "refresh_expires_at"):
                d = datetime.fromisoformat(data[f])
                check(f == "expires_at" or d > now, f"{where}: {f}",
                      f"{d:%Y-%m-%d %H:%M} UTC" + (" (expired, renewed automatically)"
                                                   if f == "expires_at" and d <= now else ""))


def online() -> None:
    section("Online calls (read-only)")
    try:
        import youtube
        resp = youtube.service().channels().list(part="snippet", mine=True).execute()
        title = (resp.get("items") or [{}])[0].get("snippet", {}).get("title", "?")
        check(True, "YouTube: token valid", f"account \"{title}\"")
    except Exception as e:  # noqa: BLE001
        check(False, "YouTube", f"{e}")
    try:
        import tiktok
        info = tiktok.api("post/publish/creator_info/query/")
        user = info.get("creator_username") or (info.get("data") or {}).get("creator_username", "?")
        check(True, "TikTok: token valid", f"@{user}")
    except Exception as e:  # noqa: BLE001
        check(False, "TikTok", f"{e}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Self-test of the publishing machine")
    ap.add_argument("--online", action="store_true", help="also check the tokens against YouTube and TikTok")
    a = ap.parse_args()
    print(f"video-studio: {ROOT}  |  Python {sys.version.split()[0]}  |  user {os.environ.get('USER', '?')}")
    tools()
    config()
    store()
    secrets_present()
    if a.online:
        online()
    ko = [label for ok, label in results if not ok]
    print(f"\n{len(results) - len(ko)}/{len(results)} checks OK" + (f" — to fix: {', '.join(ko)}" if ko else ""))
    return 1 if ko else 0


if __name__ == "__main__":
    raise SystemExit(main())
