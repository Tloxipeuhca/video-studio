"""Reply to YouTube comments from the publishing server.

    .venv/bin/python tools/stats/reply.py --list                     # comments waiting for an answer
    .venv/bin/python tools/stats/reply.py --interactive              # walk through them, type replies
    .venv/bin/python tools/stats/reply.py COMMENT_ID "Thanks!"       # reply to one comment
    echo "Thanks!" | .venv/bin/python tools/stats/reply.py COMMENT_ID --stdin

Comments come from the last collection (stats/latest.json, see collect.py). Each reply is posted
with the YouTube Data API (comments.insert, scope youtube.force-ssl, already granted), then the
comment is marked as answered and the statistics page is regenerated.

TikTok is not supported: its public API gives no access to comments.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "publish"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import PublishError, log, read_json  # noqa: E402

STATS = ROOT / "stats"
LATEST = STATS / "latest.json"
MAX_LEN = 10000  # YouTube limit for a comment
P = "reply"


def load_state() -> dict:
    state = read_json(LATEST)
    if not state:
        raise PublishError("No collected comments yet: run tools/stats/collect.py first.")
    return state


def pending(state: dict) -> list[dict]:
    return sorted((c for c in state.get("comments", []) if not c["answered"]),
                  key=lambda c: c.get("published") or "")


def find(state: dict, comment_id: str) -> dict:
    for c in state.get("comments", []):
        if c["id"] == comment_id:
            return c
    raise PublishError(f"Unknown comment id {comment_id!r} (run collect.py to refresh the list).")


def check_text(text: str) -> str:
    text = text.strip()
    if not text:
        raise PublishError("Empty reply.")
    if len(text) > MAX_LEN:
        raise PublishError(f"Reply too long ({len(text)} characters, maximum {MAX_LEN}).")
    return text


def post_reply(comment_id: str, text: str, svc=None) -> dict:
    """Posts a reply under a top-level comment. Returns the created comment resource."""
    if svc is None:
        import youtube
        svc = youtube.service()
    body = {"snippet": {"parentId": comment_id, "textOriginal": check_text(text)}}
    return svc.comments().insert(part="snippet", body=body).execute()


def mark_answered(state: dict, comment_id: str) -> None:
    for c in state.get("comments", []):
        if c["id"] == comment_id:
            c["answered"] = True
            c["replies"] = int(c.get("replies") or 0) + 1
    LATEST.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


def refresh_page(state: dict) -> None:
    from collect import load_history
    from render import render
    (STATS / "index.html").write_text(render(state, load_history()), encoding="utf-8")


def titles(state: dict) -> dict:
    return {v["id"]: v["title"] for v in state.get("videos", []) if v["platform"] == "youtube"}


def show(c: dict, video_titles: dict) -> None:
    print(f"\n[{c['id']}]  {c['author']}  ·  {c.get('published', '')[:16].replace('T', ' ')}  ·  "
          f"{video_titles.get(c['video_id'], c['video_id'])}")
    print(f"  {c['text']}")


def send(state: dict, c: dict, text: str) -> None:
    res = post_reply(c["id"], text)
    mark_answered(state, c["id"])
    log(P, f"Reply posted (id {res.get('id')}).")


def interactive(state: dict) -> int:
    todo, vt, sent = pending(state), titles(state), 0
    if not todo:
        print("No comment waiting for an answer.")
        return 0
    print(f"{len(todo)} comment(s) waiting. Type a reply, Enter to skip, q to quit.")
    for c in todo:
        show(c, vt)
        try:
            text = input("  reply> ").strip()
        except EOFError:
            break
        if text.lower() == "q":
            break
        if not text:
            continue
        if input(f"  Post this reply publicly? [y/N] ").strip().lower() != "y":
            print("  Skipped.")
            continue
        try:
            send(state, c, text)
            sent += 1
        except Exception as e:  # noqa: BLE001 - keep going with the next comment
            log(P, f"ERROR: {e}")
    if sent:
        refresh_page(state)
    print(f"\n{sent} reply(ies) posted.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Reply to YouTube comments")
    ap.add_argument("comment_id", nargs="?")
    ap.add_argument("text", nargs="?")
    ap.add_argument("--stdin", action="store_true", help="read the reply text from standard input (UTF-8)")
    ap.add_argument("--list", action="store_true", help="list the comments waiting for an answer")
    ap.add_argument("--interactive", action="store_true", help="walk through pending comments")
    a = ap.parse_args()
    try:
        state = load_state()
        if a.list:
            todo, vt = pending(state), titles(state)
            for c in todo:
                show(c, vt)
            print(f"\n{len(todo)} comment(s) waiting for an answer.")
            return 0
        if a.interactive:
            return interactive(state)
        if not a.comment_id:
            ap.error("give a comment id (see --list), or use --interactive")
        text = sys.stdin.buffer.read().decode("utf-8") if a.stdin else (a.text or "")
        c = find(state, a.comment_id)
        send(state, c, text)
        refresh_page(state)
        return 0
    except PublishError as e:
        log(P, f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        raise SystemExit(130)
