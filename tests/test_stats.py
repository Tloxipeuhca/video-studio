"""Statistics tests: TikTok matching, answered comments, 24-hour change, HTML page."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "stats"))

import collect  # noqa: E402
import render  # noqa: E402

LOCAL = [
    {"folder": "2026-11-25_harbour-sunset", "title": "Sunset over the harbour 🌅",
     "caption": "Sunset over the harbour 🌅 Ten seconds of calm", "youtube_id": "yt1",
     "tiktok_id": "v_inbox_123", "tiktok_at": "2026-11-25T18:00:00+00:00"},
    {"folder": "2026-12-01_city-walk", "title": "City walk", "caption": "A walk through the old town",
     "youtube_id": None, "tiktok_id": None, "tiktok_at": None},
]


def test_match_tiktok_by_id():
    assert collect.match_tiktok({"id": "v_inbox_123", "title": "x"}, LOCAL) == "2026-11-25_harbour-sunset"


def test_match_tiktok_by_caption():
    v = {"id": "7400000000", "title": "Sunset over the harbour 🌅 Ten seconds of calm #sunset #fyp",
         "published": "2026-11-25T19:00:00+00:00"}
    assert collect.match_tiktok(v, LOCAL) == "2026-11-25_harbour-sunset"
    assert collect.match_tiktok({"id": "1", "title": "Something else entirely"}, LOCAL) is None


def _thread(author_channel, reply_channels=()):
    return {"snippet": {"videoId": "yt1", "totalReplyCount": len(reply_channels), "topLevelComment": {
        "id": "c1", "snippet": {"authorDisplayName": "Bob", "authorChannelId": {"value": author_channel},
                                "textDisplay": "lol <b>", "publishedAt": "2026-11-26T10:00:00Z", "likeCount": 2}}},
        "replies": {"comments": [{"snippet": {"authorChannelId": {"value": r}}} for r in reply_channels]}}


def test_youtube_comment_answered():
    assert not collect.youtube_thread(_thread("UCbob"), "UCme")["answered"]
    assert not collect.youtube_thread(_thread("UCbob", ["UCalice"]), "UCme")["answered"]
    assert collect.youtube_thread(_thread("UCbob", ["UCme"]), "UCme")["answered"]
    assert collect.youtube_thread(_thread("UCme"), "UCme")["answered"]   # my own comment
    c = collect.youtube_thread(_thread("UCbob"), "UCme")
    assert c["url"] == "https://www.youtube.com/watch?v=yt1&lc=c1"


HISTORY = [
    {"ts": "2026-11-25T00:00:00+00:00", "platform": "youtube", "id": "yt1", "views": 100, "likes": 1, "comments": 0, "shares": None},
    {"ts": "2026-11-25T12:00:00+00:00", "platform": "youtube", "id": "yt1", "views": 150, "likes": 2, "comments": 0, "shares": None},
    {"ts": "2026-11-26T12:00:00+00:00", "platform": "youtube", "id": "yt1", "views": 400, "likes": 9, "comments": 1, "shares": None},
]


def test_delta_24h():
    pts = render.series(HISTORY, "youtube", "yt1")
    assert render.delta_24h(pts, "views") == 250        # 400 - sample from 24 h earlier (150)
    assert render.delta_24h(pts[:1], "views") is None   # a single sample
    assert render.delta_24h(pts, "shares") is None      # not provided by YouTube


def test_render_page():
    state = {"collected_at": "2026-11-26T12:00:00+00:00", "errors": ["TikTok: video.list scope missing"],
             "videos": [{"platform": "youtube", "id": "yt1", "title": "Sunset <harbour>", "published": "2026-11-25T10:00:00+00:00",
                         "privacy": "public", "url": "https://www.youtube.com/watch?v=yt1", "views": 400, "likes": 9,
                         "comments": 1, "shares": None, "folder": "2026-11-25_harbour-sunset"}],
             "comments": [collect.youtube_thread(_thread("UCbob"), "UCme")]}
    html = render.render(state, HISTORY)
    assert html.startswith("<!DOCTYPE html>")
    assert "Sunset &lt;harbour&gt;" in html and "lol &lt;b&gt;" in html          # HTML escaping
    assert "to answer" in html and "+250" in html and "<polyline" in html
    assert "video.list scope missing" in html
    assert "http" not in html.split("<style>")[1].split("</style>")[0]     # no external resource


def test_render_empty():
    html = render.render({"collected_at": "", "videos": [], "comments": [], "errors": []}, [])
    assert "No video collected" in html
