"""Scheduling tests ("schedule" field of publish.json) and the --due filter."""
import json
from datetime import datetime, timedelta, timezone

import pytest

import common
from common import PublishError, is_due, parse_schedule

NOW = datetime(2026, 11, 28, 17, 0, tzinfo=timezone.utc)


def test_no_schedule_never_due():
    assert not is_due({}, NOW)
    assert not is_due({"schedule": ""}, NOW)


def test_aware_dates():
    assert is_due({"schedule": "2026-11-28T17:00:00+00:00"}, NOW)
    assert is_due({"schedule": "2026-11-28T17:59:00+01:00"}, NOW)       # 16:59 UTC
    assert not is_due({"schedule": "2026-11-28T18:01:00+01:00"}, NOW)   # 17:01 UTC


def test_naive_date_is_local_time():
    dt = parse_schedule("2026-11-28T18:00")
    assert dt.tzinfo is not None
    assert dt.replace(tzinfo=None) == datetime(2026, 11, 28, 18, 0)


def test_invalid_date():
    with pytest.raises(PublishError, match="Invalid"):
        parse_schedule("tomorrow 6pm")


def _video(tmp_path, schedule=None, published=None):
    d = tmp_path / "videos" / "2026-11-28_test"
    (d / "output").mkdir(parents=True)
    (d / "output" / "clip.mp4").write_bytes(b"x")
    meta = {"video": "output/clip.mp4", "title": "t"}
    if schedule:
        meta["schedule"] = schedule
    (d / "publish.json").write_text(json.dumps(meta), encoding="utf-8")
    if published:
        (d / "published.json").write_text(json.dumps(published), encoding="utf-8")
    return d / "output" / "clip.mp4"


def test_due_filter(tmp_path, monkeypatch):
    import run
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert run._due(_video(tmp_path / "a", past), ["youtube", "tiktok"])
    assert not run._due(_video(tmp_path / "b", future), ["youtube", "tiktok"])
    assert not run._due(_video(tmp_path / "c"), ["youtube", "tiktok"])
    done = {"youtube": {"url": "u"}, "tiktok": {"url": "t"}}
    assert not run._due(_video(tmp_path / "d", past, done), ["youtube", "tiktok"])
    assert run._due(_video(tmp_path / "e", past, {"youtube": {"url": "u"}}), ["youtube", "tiktok"])


def test_single_instance(tmp_path):
    pytest.importorskip("fcntl")
    lock = tmp_path / ".lock"
    with common.single_instance(lock) as first:
        assert first
        with common.single_instance(lock) as second:
            assert not second
