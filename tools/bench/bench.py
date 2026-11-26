#!/usr/bin/env python3
"""bench.py - Performance test of a video edit, identical on Windows and Linux.

Usage: python tools/bench/bench.py [runs] --script PATH --source PATH   (default: 3 runs)

Runs the editing script several times with the same source and reports the timings, with the
machine details (CPU, RAM, FFmpeg version, hardware acceleration). Results are written to
tools/bench/results/<machine>.txt and .json. The rendered video goes to a temporary folder:
nothing is overwritten in output/.
"""
import argparse
import json
import os
import platform
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def sh(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception as e:  # noqa: BLE001
        return f"n/a ({e})"


def cpu_name():
    if sys.platform == "win32":
        return sh(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"])
    try:
        lines = Path("/proc/cpuinfo").read_text().splitlines()
        for key in ("model name", "hardware", "model"):   # "model name" first (x86), otherwise ARM
            for line in lines:
                if line.lower().startswith(key):
                    return line.split(":", 1)[1].strip()
    except Exception:  # noqa: BLE001
        pass
    return platform.processor()


def ram_gb():
    try:
        if sys.platform == "win32":
            v = sh(["powershell", "-NoProfile", "-Command",
                    "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"])
            return round(int(v) / 2**30, 1)
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30, 1)
    except Exception:  # noqa: BLE001
        return None


def main():
    ap = argparse.ArgumentParser(description="Editing performance test")
    ap.add_argument("runs", nargs="?", type=int, default=3)
    ap.add_argument("--script", type=Path, required=True, help="editing script, called as: script SOURCE OUTPUT")
    ap.add_argument("--source", type=Path, required=True, help="source video")
    a = ap.parse_args()
    for f in (a.script, a.source):
        if not f.is_file():
            sys.exit(f"[ERROR] not found: {f}")
    if not shutil.which("ffmpeg"):
        sys.exit("[ERROR] ffmpeg not in PATH")
    host = socket.gethostname()
    info = dict(machine=host, os=platform.platform(), cpu=cpu_name(), cores=os.cpu_count(),
                ram_gb=ram_gb(), python=platform.python_version(),
                ffmpeg=sh(["ffmpeg", "-hide_banner", "-version"]).splitlines()[0],
                hwaccels=sh(["ffmpeg", "-hide_banner", "-hwaccels"]).replace("\n", " "))
    print(json.dumps(info, indent=2, ensure_ascii=False))
    times = []
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "bench.mp4"
        for i in range(1, a.runs + 1):
            t0 = time.perf_counter()
            r = subprocess.run([sys.executable, str(a.script), str(a.source), str(out)])
            dt = time.perf_counter() - t0
            if r.returncode != 0:
                sys.exit(f"[ERROR] run {i} failed (exit code {r.returncode})")
            times.append(round(dt, 2))
            print(f"Run {i}/{a.runs}: {dt:.2f} s")
        size = out.stat().st_size
    info.update(runs_s=times, median_s=statistics.median(times), min_s=min(times), output_bytes=size)
    res = Path(__file__).resolve().parent / "results"
    res.mkdir(exist_ok=True)
    (res / f"{host}.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    (res / f"{host}.txt").write_text("\n".join(f"{k}: {v}" for k, v in info.items()) + "\n", encoding="utf-8")
    print(f"\nMedian: {info['median_s']} s  ->  {res / (host + '.txt')}")


if __name__ == "__main__":
    main()
