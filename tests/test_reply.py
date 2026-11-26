"""Tests for replying to YouTube comments (no network: fake YouTube service)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "stats"))

import reply  # noqa: E402
from common import PublishError  # noqa: E402


class FakeService:
    def __init__(self):
        self.calls = []

    def comments(self):
        return self

    def insert(self, part, body):
        self.calls.append((part, body))
        return self

    def execute(self):
        return {"id": "reply1"}


STATE = {"videos": [{"platform": "youtube", "id": "yt1", "title": "Clip"}], "comments": [
    {"id": "c2", "video_id": "yt1", "author": "B", "text": "two", "published": "2026-11-26T10:00:00+00:00",
     "likes": 0, "replies": 0, "answered": False},
    {"id": "c1", "video_id": "yt1", "author": "A", "text": "one", "published": "2026-11-25T10:00:00+00:00",
     "likes": 0, "replies": 0, "answered": False},
    {"id": "c3", "video_id": "yt1", "author": "C", "text": "done", "published": "2026-11-24T10:00:00+00:00",
     "likes": 0, "replies": 1, "answered": True}]}


def test_pending_oldest_first():
    assert [c["id"] for c in reply.pending(STATE)] == ["c1", "c2"]


def test_post_reply_body():
    svc = FakeService()
    assert reply.post_reply("c1", "  Thanks 🙏  ", svc)["id"] == "reply1"
    part, body = svc.calls[0]
    assert part == "snippet"
    assert body == {"snippet": {"parentId": "c1", "textOriginal": "Thanks 🙏"}}


def test_reject_empty_or_too_long():
    with pytest.raises(PublishError, match="Empty"):
        reply.check_text("   ")
    with pytest.raises(PublishError, match="too long"):
        reply.check_text("x" * (reply.MAX_LEN + 1))


def test_unknown_comment():
    with pytest.raises(PublishError, match="Unknown comment"):
        reply.find(STATE, "nope")


def test_mark_answered(tmp_path, monkeypatch):
    monkeypatch.setattr(reply, "LATEST", tmp_path / "latest.json")
    state = json.loads(json.dumps(STATE))
    reply.mark_answered(state, "c1")
    saved = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    c1 = next(c for c in saved["comments"] if c["id"] == "c1")
    assert c1["answered"] and c1["replies"] == 1
    assert [c["id"] for c in reply.pending(saved)] == ["c2"]
