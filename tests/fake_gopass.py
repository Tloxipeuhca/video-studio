"""Fake gopass for the tests: reproduces the behaviour of "gopass cat".

- stdin is a pipe                 -> its content is written to the secret (like gopass)
- stdin is a device (/dev/null) or a terminal -> read
Storage: one file per key in $FAKE_GOPASS_DIR. Every call is logged (argv only) in
$FAKE_GOPASS_DIR/_argv.log, to check that no value ever goes through the command line.
"""
import os
import stat
import sys
from pathlib import Path

store = Path(os.environ["FAKE_GOPASS_DIR"])
store.mkdir(parents=True, exist_ok=True)
with open(store / "_argv.log", "a", encoding="utf-8") as log:
    log.write(" ".join(sys.argv[1:]) + "\n")

args = sys.argv[1:]
if args[:1] == ["version"]:
    print("gopass 1.15.0 (fake)"); sys.exit(0)
if args[:1] == ["mounts"]:
    print("gopass\n├── coffre (/tmp/coffre)"); sys.exit(0)
if args[:2] == ["rm", "-f"]:
    (store / args[2].replace("/", "__")).unlink(missing_ok=True); sys.exit(0)
if args[:1] == ["cat"] and len(args) == 2:
    path = store / args[1].replace("/", "__")
    mode = os.fstat(0).st_mode
    if stat.S_ISFIFO(mode) or stat.S_ISREG(mode):  # pipe: write
        path.write_bytes(sys.stdin.buffer.read()); sys.exit(0)
    if not path.exists():
        print(f"Error: entry is not in the password store: {args[1]}", file=sys.stderr); sys.exit(11)
    sys.stdout.buffer.write(path.read_bytes()); sys.exit(0)
print(f"fake gopass: unsupported command {args}", file=sys.stderr)
sys.exit(2)
