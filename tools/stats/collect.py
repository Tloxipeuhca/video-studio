"""Collects YouTube and TikTok statistics, keeps a dated history and builds the summary page.

    .venv/bin/python tools/stats/collect.py              # collect + stats/index.html
    .venv/bin/python tools/stats/collect.py --render     # rebuild the page without calling the APIs
    .venv/bin/python tools/stats/collect.py --no-comments

Runs on the publishing server (where the tokens are), every 6 hours via the systemd timer
video-studio-stats. Output files (stats/ folder, excluded from Git):
  history.jsonl   one line per video and per collection: counters at that time
  latest.json     last full state: videos, counters, YouTube comments
  index.html      the summary page (self-contained, no external resource)

YouTube: statistics and comments with the current token (youtube.readonly / force-ssl).
TikTok : needs the video.list scope (Display API product); skipped with a message otherwise.
TikTok comment contents are not available through the public API: only their number is collected.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "publish"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import PublishError, log, read_json  # noqa: E402
from render import render  # noqa: E402

STATS = ROOT / "stats"
P = "stats"


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


# ------------------------------------------------------------------ local videos
def local_videos() -> list[dict]:
    """Project videos: folder, title, and publication ids already known (published.json)."""
    out = []
    for meta_path in sorted((ROOT / "videos").glob("*/publish.json")):
        meta = read_json(meta_path, {}) or {}
        pub = read_json(meta_path.with_name("published.json"), {}) or {}
        out.append({"folder": meta_path.parent.name, "title": meta.get("title", ""),
                    "caption": meta.get("caption") or meta.get("title", ""),
                    "youtube_id": (pub.get("youtube") or {}).get("id"),
                    "tiktok_id": (pub.get("tiktok") or {}).get("id"),
                    "tiktok_at": (pub.get("tiktok") or {}).get("uploadedAt")})
    return out


def _norm(text: str) -> str:
    return "".join(ch for ch in (text or "").lower() if ch.isalnum())[:40]


def match_tiktok(video: dict, local: list[dict]) -> str | None:
    """Links a TikTok video to a project folder: by id, otherwise by the start of the caption.

    In draft (inbox) mode, TikTok does not return the id of the final video, so the first 20
    alphanumeric characters of the caption are compared, then the upload date breaks ties.
    """
    for lv in local:
        if lv["tiktok_id"] and lv["tiktok_id"] == video["id"]:
            return lv["folder"]
    desc = _norm(video.get("title", ""))
    candidates = [lv for lv in local
                  if desc and _norm(lv["caption"])[:20] and desc.startswith(_norm(lv["caption"])[:20])]
    if len(candidates) > 1 and video.get("published"):
        when = datetime.fromisoformat(video["published"])

        def gap(lv):
            try:
                return abs(datetime.fromisoformat(lv["tiktok_at"]) - when) if lv["tiktok_at"] else timedelta.max
            except ValueError:
                return timedelta.max
        candidates.sort(key=gap)
    return candidates[0]["folder"] if candidates else None


# ------------------------------------------------------------------------ YouTube
def youtube_collect(with_comments: bool = True) -> tuple[list[dict], list[dict], str | None]:
    import youtube
    svc = youtube.service()
    ch = svc.channels().list(part="id,contentDetails,snippet", mine=True).execute()["items"][0]
    channel_id = ch["id"]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]

    ids, token = [], None
    while True:
        page = svc.playlistItems().list(part="contentDetails", playlistId=uploads,
                                        maxResults=50, pageToken=token).execute()
        ids += [it["contentDetails"]["videoId"] for it in page.get("items", [])]
        token = page.get("nextPageToken")
        if not token:
            break

    videos = []
    for i in range(0, len(ids), 50):
        resp = svc.videos().list(part="snippet,statistics,status", id=",".join(ids[i:i + 50])).execute()
        for v in resp.get("items", []):
            st = v.get("statistics", {})
            videos.append({
                "platform": "youtube", "id": v["id"], "title": v["snippet"]["title"],
                "published": v["snippet"]["publishedAt"].replace("Z", "+00:00"),
                "privacy": v.get("status", {}).get("privacyStatus"),
                "url": f"https://www.youtube.com/watch?v={v['id']}",
                "views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)),
                "comments": int(st.get("commentCount", 0)), "shares": None})

    comments = []
    if with_comments and ids:
        token = None
        for _ in range(10):  # at most 10 pages of 100 per collection
            page = svc.commentThreads().list(part="snippet,replies", allThreadsRelatedToChannelId=channel_id,
                                             maxResults=100, order="time", textFormat="plainText",
                                             pageToken=token).execute()
            for th in page.get("items", []):
                comments.append(youtube_thread(th, channel_id))
            token = page.get("nextPageToken")
            if not token:
                break
    return videos, comments, channel_id


def youtube_thread(thread: dict, channel_id: str) -> dict:
    """A comment thread: the top-level comment, and whether the channel already answered it."""
    top = thread["snippet"]["topLevelComment"]["snippet"]
    replies = (thread.get("replies") or {}).get("comments", [])
    answered = any((r["snippet"].get("authorChannelId") or {}).get("value") == channel_id for r in replies)
    mine = (top.get("authorChannelId") or {}).get("value") == channel_id
    vid = thread["snippet"].get("videoId")
    cid = thread["snippet"]["topLevelComment"]["id"]
    return {"video_id": vid, "id": cid, "author": top.get("authorDisplayName", "?"),
            "text": top.get("textDisplay") or top.get("textOriginal", ""),
            "published": top.get("publishedAt", "").replace("Z", "+00:00"),
            "likes": int(top.get("likeCount", 0)),
            "replies": int(thread["snippet"].get("totalReplyCount", 0)),
            "answered": answered or mine,
            "url": f"https://www.youtube.com/watch?v={vid}&lc={cid}"}


# ------------------------------------------------------------------------- TikTok
TIKTOK_FIELDS = "id,title,video_description,create_time,share_url,view_count,like_count,comment_count,share_count"


def tiktok_collect() -> list[dict]:
    import tiktok
    videos, cursor = [], None
    for _ in range(20):  # at most 20 pages of 20 videos
        body = {"max_count": 20} | ({"cursor": cursor} if cursor else {})
        data = tiktok.api(f"video/list/?fields={TIKTOK_FIELDS}", body)
        for v in data.get("videos", []):
            videos.append({
                "platform": "tiktok", "id": str(v["id"]),
                "title": v.get("title") or v.get("video_description") or "",
                "published": datetime.fromtimestamp(int(v.get("create_time", 0)), timezone.utc).isoformat(),
                "privacy": None, "url": v.get("share_url"),
                "views": int(v.get("view_count", 0)), "likes": int(v.get("like_count", 0)),
                "comments": int(v.get("comment_count", 0)), "shares": int(v.get("share_count", 0))})
        if not data.get("has_more"):
            break
        cursor = data.get("cursor")
    return videos


# ------------------------------------------------------------------------ history
def append_history(videos: list[dict], ts: str) -> None:
    STATS.mkdir(exist_ok=True)
    with (STATS / "history.jsonl").open("a", encoding="utf-8") as fh:
        for v in videos:
            fh.write(json.dumps({"ts": ts, "platform": v["platform"], "id": v["id"], "views": v["views"],
                                 "likes": v["likes"], "comments": v["comments"], "shares": v["shares"]}) + "\n")


def load_history() -> list[dict]:
    path = STATS / "history.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def collect(with_comments: bool = True) -> dict:
    ts = now_utc().isoformat()
    local = local_videos()
    videos, comments, errors = [], [], []
    try:
        yv, comments, _ = youtube_collect(with_comments)
        for v in yv:
            v["folder"] = next((lv["folder"] for lv in local if lv["youtube_id"] == v["id"]), None)
        videos += yv
        log(P, f"YouTube: {len(yv)} video(s), {len(comments)} comment(s).")
    except Exception as e:  # noqa: BLE001 - one failing platform must not stop the other
        errors.append(f"YouTube: {e}")
        log(P, f"YouTube: ERROR {e}")
    try:
        tv = tiktok_collect()
        for v in tv:
            v["folder"] = match_tiktok(v, local)
        videos += tv
        log(P, f"TikTok: {len(tv)} video(s).")
    except PublishError as e:
        msg = str(e)
        if "scope" in msg.lower():
            msg = ("video.list scope missing: enable Display API in the TikTok app, add it to "
                   "VS_TIKTOK_SCOPES, then run auth_tunnel.ps1 tiktok")
        errors.append(f"TikTok: {msg}")
        log(P, f"TikTok: {msg}")
    except Exception as e:  # noqa: BLE001
        errors.append(f"TikTok: {e}")
        log(P, f"TikTok: ERROR {e}")

    if videos:
        append_history(videos, ts)
    state = {"collected_at": ts, "videos": videos, "comments": comments, "errors": errors}
    STATS.mkdir(exist_ok=True)
    (STATS / "latest.json").write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    return state


def main() -> int:
    ap = argparse.ArgumentParser(description="YouTube + TikTok statistics")
    ap.add_argument("--render", action="store_true", help="rebuild the page from latest.json, no network call")
    ap.add_argument("--no-comments", action="store_true")
    a = ap.parse_args()
    if a.render:
        state = read_json(STATS / "latest.json")
        if not state:
            log(P, "No collection recorded yet: run without --render first.")
            return 1
    else:
        state = collect(with_comments=not a.no_comments)
    out = STATS / "index.html"
    out.write_text(render(state, load_history()), encoding="utf-8")
    log(P, f"Page: {out}")
    return 1 if state.get("errors") and not state.get("videos") else 0


if __name__ == "__main__":
    raise SystemExit(main())
