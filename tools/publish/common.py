"""Helpers shared by the publishing modules."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # project root (tools/publish/ -> ../..)
SECRETS = ROOT / "secrets"  # legacy mode (plain files), see secrets_store.py


class PublishError(Exception):
    """Publishing error, reported cleanly to the launcher."""


def log(platform: str, msg: str) -> None:
    print(f"[{platform}] {msg}", flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ JSON files
def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


_STORE = None


def secret_store():
    """Secret storage (gopass or files), selected by VS_SECRETS_BACKEND (.env or environment)."""
    global _STORE
    if _STORE is None:
        from secrets_store import SecretError, make_store
        try:
            _STORE = make_store(ROOT)
        except SecretError as e:
            raise PublishError(str(e)) from None
    return _STORE


def load_secret(name: str, required: bool = True):
    from secrets_store import SecretError
    store = secret_store()
    try:
        data = store.get(name)
    except SecretError as e:
        raise PublishError(str(e)) from None
    if data is None and required:
        raise PublishError(f"Secret not found: {name} in {store.describe()}")
    return data


def save_secret(name: str, data) -> None:
    from secrets_store import SecretError
    try:
        secret_store().put(name, data)
    except SecretError as e:
        raise PublishError(str(e)) from None


def headless() -> bool:
    """True on a Linux machine without a display (server): authorization pages open on the PC via an SSH tunnel."""
    import os
    return sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY")


# ------------------------------------------------------------------ scheduling
def parse_schedule(value: str) -> datetime:
    """ISO 8601 date; without a time zone it is read in the machine's local time zone."""
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise PublishError(f"Invalid schedule date: {value!r} "
                           "(expected 2026-11-28T18:00 or 2026-11-28T18:00+01:00)") from None
    return dt.astimezone() if dt.tzinfo is None else dt


def is_due(meta: dict, now: datetime | None = None) -> bool:
    """A video is published automatically only if publish.json has "schedule" and that time has passed."""
    value = meta.get("schedule")
    if not value:
        return False
    return (now or datetime.now(timezone.utc)) >= parse_schedule(value)


class single_instance:
    """Lock preventing two simultaneous publishing runs (tokens rewritten at the same time). No-op on Windows."""

    def __init__(self, path: Path):
        self.path, self.fh = path, None

    def __enter__(self) -> bool:
        try:
            import fcntl
        except ImportError:
            return True
        self.fh = open(self.path, "w")
        try:
            fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def __exit__(self, *exc):
        if self.fh:
            self.fh.close()


# -------------------------------------------------------------------- metadata
def meta_path_for(video: Path) -> Path:
    """Metadata file of a video.

    Standard layout: videos/<folder>/publish.json, with "video": "output/xxx.mp4".
    Legacy layout still accepted: <video>.publish.json next to the video.
    """
    video = video.resolve()
    for folder in (video.parent, video.parent.parent):
        cand = folder / "publish.json"
        if cand.exists():
            target = (read_json(cand, {}) or {}).get("video")
            if target and (folder / target).resolve() == video:
                return cand
    return video.with_suffix(".publish.json")


def video_for(path: Path) -> Path:
    """Accepts a video folder, a publish.json file or the video file itself."""
    path = path.resolve()
    meta = path / "publish.json" if path.is_dir() else path
    if meta.name == "publish.json":
        data = read_json(meta)
        if not data or not data.get("video"):
            raise PublishError(f"{meta}: \"video\" field missing, or file not found.")
        return (meta.parent / data["video"]).resolve()
    return path


def load_meta(video: Path, meta_path: Path | None = None) -> dict:
    path = meta_path or meta_path_for(video)
    meta = read_json(path)
    if meta is None:
        raise PublishError(f"Metadata not found: {path}")
    meta["_dir"] = path.parent
    return meta


def platform_meta(meta: dict, platform: str) -> dict:
    return meta.get(platform, {}) or {}


def caption_for(meta: dict, platform: str) -> str:
    """Caption = caption + common hashtags + platform-specific hashtags."""
    pm = platform_meta(meta, platform)
    text = pm.get("caption") or meta.get("caption") or meta.get("title", "")
    tags = list(meta.get("hashtags", [])) + list(pm.get("extra_hashtags", []))
    tags = [t if t.startswith("#") else f"#{t}" for t in tags]
    return (text + ("\n\n" + " ".join(dict.fromkeys(tags)) if tags else "")).strip()


# ---------------------------------------------------------------- publish log
def published_path(video: Path) -> Path:
    meta = meta_path_for(video)
    if meta.name == "publish.json":
        return meta.with_name("published.json")
    return video.with_suffix(".published.json")


def published_entry(video: Path, platform: str) -> dict | None:
    return (read_json(published_path(video), {}) or {}).get(platform)


def record(video: Path, platform: str, result: dict) -> None:
    path = published_path(video)
    data = read_json(path, {}) or {}
    data[platform] = {**result, "uploadedAt": now_iso()}
    write_json(path, data)


def die(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)


# ------------------------------------------------------------------- cover image
DEFAULT_COVER_MS = 4000  # default rule: frame at 4 s (capped to the video duration)


def video_duration_ms(video: Path) -> int | None:
    import shutil
    import subprocess
    exe = shutil.which("ffprobe")
    if not exe:
        return None
    out = subprocess.run([exe, "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(video)],
                         capture_output=True, text=True).stdout.strip()
    try:
        return int(float(out) * 1000)
    except ValueError:
        return None


def extract_frame(video: Path, time_ms: int, out: Path) -> Path | None:
    import shutil
    import subprocess
    exe = shutil.which("ffmpeg")
    if not exe:
        return None
    subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{time_ms / 1000:.3f}",
                    "-i", str(video), "-frames:v", "1", "-q:v", "2", str(out)], check=False)
    return out if out.exists() else None


def resolve_cover(video: Path, meta: dict, platform: str) -> dict:
    """Cover image to use for a platform.

    Priority: platform values > common JSON values > default rule.
      - image    : local file ("thumbnail"), otherwise a frame extracted from the video at time_ms
      - time_ms  : position in the video ("cover_time_ms"), otherwise DEFAULT_COVER_MS
      - url      : public image URL ("cover_url"), the only way to send an image to Instagram
      - from_json: True if an image was given in the JSON
    """
    pm = platform_meta(meta, platform)
    time_ms = pm.get("cover_time_ms", meta.get("cover_time_ms"))
    image_name = pm.get("thumbnail", meta.get("thumbnail"))
    url = pm.get("cover_url", meta.get("cover_url"))

    if time_ms is None:
        time_ms = DEFAULT_COVER_MS
        dur = video_duration_ms(video)
        if dur:
            time_ms = min(time_ms, max(dur - 100, 0))

    image = None
    if image_name:
        image = (meta["_dir"] / image_name).resolve()
        if not image.exists():
            log(platform, f"Cover image not found ({image}), using the default rule.")
            image = None
    from_json = image is not None
    if image is None:
        image = extract_frame(video, int(time_ms), video.with_suffix(".cover.jpg"))
    return {"image": image, "time_ms": int(time_ms), "url": url, "from_json": from_json}


# ---------------------------------------------------------- authorization ports
LOOPBACK = "127.0.0.1"  # explicit: "localhost" may resolve to IPv6 and reach another app


def port_in_use(port: int) -> bool:
    """True if an application already listens on this port, over IPv4 or IPv6."""
    import socket
    for family, addr in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.3)
                if sock.connect_ex((addr, port)) == 0:
                    return True
        except OSError:
            pass
    return False


def free_port(candidates, platform: str = "auth") -> int:
    """First port of the list that is really free (checked before use)."""
    import socket
    for port in candidates:
        if port_in_use(port):
            log(platform, f"Port {port} already used by another application, trying the next one.")
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((LOOPBACK, port))
                return port
            except OSError:
                continue
    raise PublishError(f"No free port among {tuple(candidates)} for the authorization.")


# ------------------------------------------------------------- authorization browser
def setup_auth_browser() -> None:
    """Opens authorization pages in the Chrome profile set in .env.

    .env: VS_CHROME_PATH=C:\\...\\chrome.exe  and  VS_CHROME_PROFILE=Profile 2
    Without these settings (or on a server without a display), the default browser is used.
    """
    import webbrowser
    from settings import get
    exe, profile = get("VS_CHROME_PATH"), get("VS_CHROME_PROFILE")
    if not exe or not Path(exe).exists():
        if exe and not headless():
            log("auth", f"Chrome not found ({exe}): using the default browser.")
        return
    args = [exe] + ([f"--profile-directory={profile}"] if profile else [])
    webbrowser.register("video-studio-chrome", None, webbrowser.BackgroundBrowser(args), preferred=True)
    log("auth", f"Authorization in Chrome, profile \"{profile or 'default'}\".")
