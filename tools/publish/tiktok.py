"""TikTok publishing with the Content Posting API (Direct Post, or "inbox" draft).

    python tools/publish/tiktok.py --auth-only
    python tools/publish/tiktok.py --creator-info
    python tools/publish/tiktok.py VIDEO.mp4 [--mode direct|inbox] [--privacy SELF_ONLY] [--dry-run] [--force]

As long as the app has not been audited by TikTok:
  - direct mode: the account must be PRIVATE and the video is posted as SELF_ONLY;
  - inbox mode : the video lands as a draft in the TikTok app, to be confirmed with one tap.
"""
from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import math
import secrets as pysecrets
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path

from common import (video_for, PublishError, caption_for, die, load_meta, load_secret, log,
                    platform_meta, published_entry, record, resolve_cover, save_secret,
                    LOOPBACK, free_port, setup_auth_browser)

P = "tiktok"
API = "https://open.tiktokapis.com/v2"
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
APP_NAME = "tiktok_app.json"      # {"client_key": "...", "client_secret": "..."}
TOKEN_NAME = "tiktok.token.json"
# Redirect URI to declare in Login Kit (wildcard port): http://127.0.0.1:*/callback/
REDIRECT_PORTS = (47821, 47822, 47823, 47824, 47825)


def _scopes() -> str:
    """Must match the TikTok app scopes exactly (otherwise a "scope" error).

    video.list (statistics, tools/stats) requires the Display API product in the TikTok app:
    add it to VS_TIKTOK_SCOPES in .env once the product is enabled, then authorize again.
    """
    from settings import get
    return get("VS_TIKTOK_SCOPES") or "user.info.basic,video.publish,video.upload"


SCOPES = _scopes()
MB = 1024 * 1024
CHUNK = 10 * MB


def _requests():
    import requests
    return requests


def _check(resp) -> dict:
    try:
        data = resp.json()
    except ValueError:
        raise PublishError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    err = data.get("error") or {}
    if resp.status_code >= 400 or (isinstance(err, dict) and err.get("code") not in (None, "ok")):
        msg = err.get("message") if isinstance(err, dict) else err
        code = err.get("code") if isinstance(err, dict) else data.get("error")
        raise PublishError(f"HTTP {resp.status_code}: {code}: {msg or data.get('error_description')}")
    return data


# --------------------------------------------------------------------------- auth
class _Callback(http.server.BaseHTTPRequestHandler):
    result: dict = {}

    def do_GET(self):  # noqa: N802
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _Callback.result = {k: v[0] for k, v in q.items()}
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("<h2>TikTok authorization received, you can close this tab.</h2>".encode())

    def log_message(self, *args):
        pass


def _save_token(data: dict) -> dict:
    now = datetime.now(timezone.utc)
    tok = {"access_token": data["access_token"], "refresh_token": data["refresh_token"],
           "open_id": data.get("open_id"), "scope": data.get("scope"),
           "expires_at": (now + timedelta(seconds=int(data["expires_in"]) - 120)).isoformat(),
           "refresh_expires_at": (now + timedelta(seconds=int(data["refresh_expires_in"]))).isoformat()}
    save_secret(TOKEN_NAME, tok)
    return tok


def authorize() -> dict:
    app = load_secret(APP_NAME)
    verifier = pysecrets.token_urlsafe(64)[:96]
    challenge = hashlib.sha256(verifier.encode()).hexdigest()  # TikTok desktop: SHA256 as hex
    state = pysecrets.token_urlsafe(16)
    port = free_port(REDIRECT_PORTS, P)
    redirect_uri = f"http://{LOOPBACK}:{port}/callback/"
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_key": app["client_key"], "response_type": "code", "scope": SCOPES,
        "redirect_uri": redirect_uri, "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256"})

    srv = http.server.HTTPServer((LOOPBACK, port), _Callback)
    th = threading.Thread(target=srv.handle_request, daemon=True)
    th.start()
    setup_auth_browser()
    log(P, "Opening the browser for authorization…")
    print(f"If the browser does not open, open this address:\n{url}", flush=True)
    webbrowser.open(url)
    th.join(timeout=300)
    srv.server_close()
    res = _Callback.result
    if not res:
        raise PublishError("No authorization response (5 minute timeout).")
    if res.get("state") != state:
        raise PublishError("Invalid state parameter: authorization rejected.")
    if "code" not in res:
        raise PublishError(f"Authorization denied: {res.get('error')} {res.get('error_description', '')}")

    data = _check(_requests().post(f"{API}/oauth/token/", timeout=60, data={
        "client_key": app["client_key"], "client_secret": app["client_secret"],
        "code": res["code"], "grant_type": "authorization_code",
        "redirect_uri": redirect_uri, "code_verifier": verifier}))
    tok = _save_token(data)
    log(P, f"Authorized (scopes: {tok['scope']}).")
    return tok


def get_token() -> str:
    tok = load_secret(TOKEN_NAME, required=False)
    if not tok:
        raise PublishError("No TikTok token: run \"python tools/publish/tiktok.py --auth-only\".")
    now = datetime.now(timezone.utc)
    if now < datetime.fromisoformat(tok["expires_at"]):
        return tok["access_token"]
    if now >= datetime.fromisoformat(tok["refresh_expires_at"]):
        raise PublishError("Refresh token expired: run --auth-only again.")
    app = load_secret(APP_NAME)
    data = _check(_requests().post(f"{API}/oauth/token/", timeout=60, data={
        "client_key": app["client_key"], "client_secret": app["client_secret"],
        "grant_type": "refresh_token", "refresh_token": tok["refresh_token"]}))
    return _save_token(data)["access_token"]


def api(path: str, body: dict | None = None) -> dict:
    r = _requests().post(f"{API}/{path.lstrip('/')}", json=body or {}, timeout=60, headers={
        "Authorization": f"Bearer {get_token()}",
        "Content-Type": "application/json; charset=UTF-8"})
    return _check(r).get("data", {})


# ------------------------------------------------------------------- publishing
def _source_info(size: int) -> dict:
    if size <= 64 * MB:
        return {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}
    return {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": CHUNK,
            "total_chunk_count": size // CHUNK}  # the last chunk takes the remainder


def _upload(url: str, video: Path, info: dict) -> None:
    size, chunk, n = info["video_size"], info["chunk_size"], info["total_chunk_count"]
    with video.open("rb") as fh:
        for i in range(n):
            start = i * chunk
            end = size - 1 if i == n - 1 else start + chunk - 1
            fh.seek(start)
            part = fh.read(end - start + 1)
            r = _requests().put(url, data=part, timeout=600, headers={
                "Content-Type": "video/mp4", "Content-Length": str(len(part)),
                "Content-Range": f"bytes {start}-{end}/{size}"})
            if r.status_code not in (200, 201, 206):
                raise PublishError(f"Uploading chunk {i + 1}/{n}: HTTP {r.status_code} {r.text[:200]}")
            log(P, f"Upload: {math.floor((end + 1) / size * 100)} %")


def publish(video: Path, meta: dict, *, private: bool = False, dry_run: bool = False,
            mode: str | None = None, **_ignored) -> dict:
    pm = platform_meta(meta, P)
    mode = mode or pm.get("mode", "direct")
    privacy = "SELF_ONLY" if private else pm.get("privacy", "SELF_ONLY")
    size = video.stat().st_size
    info = _source_info(size)
    cover = resolve_cover(video, meta, P)
    post_info = {"title": caption_for(meta, P), "privacy_level": privacy,
                 "disable_comment": bool(pm.get("disable_comment", False)),
                 "disable_duet": bool(pm.get("disable_duet", False)),
                 "disable_stitch": bool(pm.get("disable_stitch", False))}
    post_info["video_cover_timestamp_ms"] = cover["time_ms"]  # the API does not accept an image
    if cover["from_json"] and pm.get("cover_time_ms", meta.get("cover_time_ms")) is None:
        log(P, f"TikTok does not accept an image: using the video frame at {cover['time_ms']} ms.")

    if dry_run:
        body = {"post_info": post_info, "source_info": info} if mode == "direct" else {"source_info": info}
        log(P, f"Dry run ({mode} mode):\n" + json.dumps(body, ensure_ascii=False, indent=2))
        return {}

    uname = pm.get("username", "")
    if mode == "direct":
        ci = api("post/publish/creator_info/query/")
        options = ci.get("privacy_level_options", [])
        if privacy not in options:
            log(P, f"Privacy {privacy} not allowed ({options}), falling back to SELF_ONLY.")
            post_info["privacy_level"] = "SELF_ONLY"
        uname = ci.get("creator_username") or uname
        max_s = ci.get("max_video_post_duration_sec")
        log(P, f"Account @{ci.get('creator_username')} | max duration {max_s} s")
        init = api("post/publish/video/init/", {"post_info": post_info, "source_info": info})
    else:
        init = api("post/publish/inbox/video/init/", {"source_info": info})

    publish_id, upload_url = init["publish_id"], init["upload_url"]
    _upload(upload_url, video, info)

    for _ in range(120):  # 10 minutes
        st = api("post/publish/status/fetch/", {"publish_id": publish_id})
        status = st.get("status")
        if status == "PUBLISH_COMPLETE":
            ids = st.get("publicaly_available_post_id") or st.get("publicly_available_post_id") or []
            url = f"https://www.tiktok.com/@{uname}/video/{ids[0]}" if ids else None
            log(P, f"Published ({post_info['privacy_level']}): {url or 'link available in the app'}")
            return {"id": ids[0] if ids else publish_id, "url": url, "mode": mode,
                    "privacy": post_info["privacy_level"]}
        if status == "SEND_TO_USER_INBOX":
            log(P, "Draft sent: open the TikTok app (notifications) to finish posting.")
            return {"id": publish_id, "url": None, "mode": "inbox"}
        if status == "FAILED":
            raise PublishError(f"TikTok failure: {st.get('fail_reason')}")
        time.sleep(5)
    raise PublishError("TikTok processing took too long (10 min).")


# --------------------------------------------------------------------------- CLI
def main() -> None:
    ap = argparse.ArgumentParser(description="TikTok publishing")
    ap.add_argument("video", nargs="?", type=Path)
    ap.add_argument("--meta", type=Path)
    ap.add_argument("--mode", choices=["direct", "inbox"])
    ap.add_argument("--privacy", choices=["SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS",
                                          "FOLLOWER_OF_CREATOR", "PUBLIC_TO_EVERYONE"])
    ap.add_argument("--auth-only", action="store_true")
    ap.add_argument("--creator-info", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--test", action="store_true", help="test upload: SELF_ONLY, log not modified")
    a = ap.parse_args()
    try:
        if a.auth_only:
            authorize()
            return
        if a.creator_info:
            log(P, json.dumps(api("post/publish/creator_info/query/"), indent=2, ensure_ascii=False))
            return
        if not a.video:
            ap.error("video path required")
        video = video_for(a.video)
        prev = published_entry(video, P)
        if prev and not a.force and not a.dry_run and not a.test:
            log(P, f"Already published ({prev.get('url') or 'manually'}). Use --force to upload again.")
            return
        meta = load_meta(video, a.meta)
        if a.privacy:
            meta.setdefault(P, {})["privacy"] = a.privacy
        res = publish(video, meta, mode=a.mode, private=a.test, dry_run=a.dry_run)
        if res and a.test:
            log(P, "--test mode: log not modified.")
        elif res:
            record(video, P, res)
    except PublishError as e:
        die(f"[{P}] ERROR: {e}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted (Ctrl+C).")
        raise SystemExit(130)
