"""Launcher: publishes one or more videos on every platform.

    python tools/publish/run.py videos/<folder>                 (folder, publish.json or .mp4)
    python tools/publish/run.py --scan videos                   (every video not yet published)
    python tools/publish/run.py --scan videos --due             (scheduled videos whose time has come)
    Options: --platforms youtube,tiktok,instagram  --test  --dry-run  --force  --due

--due  : keeps only the videos whose publish.json has a "schedule" (ISO date) already reached and
         that are not yet published on every requested platform. Used by the systemd timer of the
         Linux server (tools/deploy/systemd/).
--test : YouTube private, TikTok SELF_ONLY, Instagram skipped (no private mode).
         The published.json log is not modified.
An error on one platform does not stop the others.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import instagram
import tiktok
import youtube
from common import (ROOT, PublishError, is_due, load_meta, log, published_entry, record,
                    single_instance, video_for)

PUBLISHERS = {"youtube": youtube.publish, "instagram": instagram.publish, "tiktok": tiktok.publish}


def find_videos(root: Path) -> list[Path]:
    """Every video with metadata under root."""
    found = []
    for m in root.rglob("publish.json"):
        try:
            found.append(video_for(m))
        except PublishError as e:
            log("run", f"skipped: {e}")
    for m in root.rglob("*.publish.json"):  # legacy layout
        v = m.with_name(m.name.replace(".publish.json", ".mp4"))
        if v.exists():
            found.append(v.resolve())
    return sorted(set(v for v in found if v.exists()))


def _due(video: Path, platforms: list[str]) -> bool:
    try:
        meta = load_meta(video)
        return is_due(meta) and any(not published_entry(video, p) for p in platforms)
    except PublishError as e:
        log("run", f"skipped: {e}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Multi-platform publishing")
    ap.add_argument("videos", nargs="*", type=Path)
    ap.add_argument("--scan", type=Path)
    ap.add_argument("--platforms", default="youtube,tiktok")
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--due", action="store_true", help="only scheduled videos whose time has come")
    a = ap.parse_args()
    with single_instance(ROOT / ".publish.lock") as got:
        if not got:
            log("run", "Another publishing run is in progress: aborting.")
            return 0
        return _run(ap, a)


def _run(ap, a) -> int:
    try:
        videos = [video_for(v) for v in a.videos]
    except PublishError as e:
        ap.error(str(e))
    videos += find_videos(a.scan.resolve()) if a.scan else []
    if not videos and not a.due:
        ap.error("no video (give paths or --scan FOLDER)")
    platforms = [p.strip() for p in a.platforms.split(",") if p.strip()]
    unknown = set(platforms) - PUBLISHERS.keys()
    if unknown:
        ap.error(f"unknown platforms: {', '.join(sorted(unknown))}")
    if a.due:
        videos = [v for v in videos if _due(v, platforms)]
        if not videos:
            return 0  # nothing to do: stay silent (runs every 15 min)

    failures = 0
    for video in videos:
        print(f"\n=== {video.name} ===")
        try:
            meta = load_meta(video)
        except PublishError as e:
            log("run", f"ERROR: {e}")
            failures += 1
            continue
        for p in platforms:
            if a.test and p == "instagram":
                log(p, "no private publishing available, skipped in --test mode.")
                continue
            prev = published_entry(video, p)
            if prev and not a.force and not a.dry_run:
                log(p, f"already published ({prev.get('url') or 'manually'}), skipped.")
                continue
            try:
                res = PUBLISHERS[p](video, meta, private=a.test, dry_run=a.dry_run)
                if res and a.test:
                    log(p, f"--test mode: log not modified (test copy: {res.get('url')}).")
                elif res:
                    record(video, p, res)
            except PublishError as e:
                log(p, f"ERROR: {e}")
                failures += 1
            except Exception as e:  # unexpected error: carry on with the others
                log(p, f"Unexpected ERROR: {e!r}")
                failures += 1
    print(f"\nDone, {failures} error(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted (Ctrl+C).")
        raise SystemExit(130)
