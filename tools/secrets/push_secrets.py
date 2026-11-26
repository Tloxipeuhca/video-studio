"""Copies the secrets of the secrets/ folder (PC) into gopass on the Linux server, over SSH.

    py tools\\secrets\\push_secrets.py                       # dry run: lists what would be copied
    py tools\\secrets\\push_secrets.py --apply               # copy, then read back and compare
    py tools\\secrets\\push_secrets.py --apply --overwrite   # also replace entries already present

Defaults read from .env: VS_SERVER, VS_GOPASS_PREFIX, VS_GOPASS_CMD
(override with --target, --prefix, --gopass-cmd).

Values only travel through the encrypted SSH stream, on the standard input of "gopass cat":
never on a command line, never in a file on the server.
The secrets/ folder is left untouched: delete it by hand once the server is validated.
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools" / "publish"))
from secrets_store import DEFAULT_PREFIX, KEYS, FileStore  # noqa: E402
from settings import get  # noqa: E402

TARGET = get("VS_SERVER")
GOPASS_CMD = get("VS_GOPASS_CMD") or "gopass"


def ssh(target: str, remote_cmd: str, payload: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["ssh", "-o", "BatchMode=yes", target, remote_cmd], input=payload,
                          capture_output=True, timeout=120,
                          stdin=subprocess.DEVNULL if payload is None else None)


def remote_read(target: str, key: str, gp: str = GOPASS_CMD):
    # </dev/null on the server: otherwise "gopass cat" takes the SSH stream for a write
    r = ssh(target, f"{gp} cat {shlex.quote(key)} </dev/null")
    if r.returncode != 0 or not r.stdout.strip():
        return None
    try:
        return json.loads(r.stdout.decode("utf-8"))
    except json.JSONDecodeError:
        return "<not JSON>"


def main() -> int:
    ap = argparse.ArgumentParser(description="secrets/ -> gopass on the Linux server")
    ap.add_argument("--target", default=TARGET)
    ap.add_argument("--prefix", default=get("VS_GOPASS_PREFIX") or DEFAULT_PREFIX)
    ap.add_argument("--gopass-cmd", default=GOPASS_CMD, help="gopass command on the server")
    ap.add_argument("--apply", action="store_true", help="really copy (dry run otherwise)")
    ap.add_argument("--overwrite", action="store_true", help="replace entries already present on the server")
    a = ap.parse_args()
    if not a.target:
        ap.error("unknown server: set VS_SERVER in .env (see .env.example) or pass --target")

    files = FileStore(ROOT / "secrets")
    gp = a.gopass_cmd
    r = ssh(a.target, f"{gp} mounts </dev/null")
    if r.returncode != 0:
        print(f"[ERROR] gopass unreachable on {a.target}: {r.stderr.decode('utf-8', 'replace').strip()}")
        print("        Check key-based SSH (BatchMode) and that gopass is in the non-interactive PATH.")
        return 1
    print(f"gopass on {a.target}:\n{r.stdout.decode('utf-8', 'replace').strip()}\n")
    if a.prefix.split("/")[0] not in r.stdout.decode("utf-8", "replace"):
        print(f"[WARNING] mount \"{a.prefix.split('/')[0]}\" is not listed above: check --prefix.")

    errors = 0
    for name, sub in KEYS.items():
        key = f"{a.prefix}/{sub}"
        data = files.get(name)
        if data is None:
            print(f"  -    {key:<45} not in secrets/, skipped")
            continue
        existing = remote_read(a.target, key, gp)
        if existing is not None and not a.overwrite:
            same = "identical" if existing == data else "DIFFERENT (--overwrite to replace)"
            print(f"  =    {key:<45} already present, {same}")
            continue
        if not a.apply:
            print(f"  +    {key:<45} would be copied ({', '.join(data.keys())})")
            continue
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        w = ssh(a.target, f"{gp} cat {shlex.quote(key)}", payload)
        if w.returncode != 0:
            print(f"  KO   {key:<45} {w.stderr.decode('utf-8', 'replace').strip()}")
            errors += 1
            continue
        ok = remote_read(a.target, key, gp) == data
        print(f"  {'OK' if ok else 'KO'}   {key:<45} {'copied and read back identical' if ok else 'read-back differs!'}")
        errors += not ok
    if not a.apply:
        print("\nDry run only: run again with --apply to copy.")
    elif not errors:
        print(f"\nCopy done. On the server: cd {get('VS_SERVER_DIR') or '<VS_SERVER_DIR>'} && "
              ".venv/bin/python tools/publish/selftest.py --online")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
