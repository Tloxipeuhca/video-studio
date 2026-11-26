"""Instagram publishing (Reels) with "Instagram API with Instagram Login".

    python tools/publish/instagram.py --set-token TOKEN    (once: long-lived token from the Meta app)
    python tools/publish/instagram.py --whoami
    python tools/publish/instagram.py VIDEO.mp4 [--dry-run] [--force]

Implemented but untested (the test account was suspended by Meta); not part of the default
platforms: add it with run.py --platforms youtube,tiktok,instagram.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from common import (video_for, PublishError, caption_for, die, load_meta, load_secret, log, now_iso,
                    platform_meta, published_entry, record, resolve_cover, save_secret)

P = "instagram"
HOSTS = {"unified": "https://graph.facebook.com", "instagram": "https://graph.instagram.com"}
VERSION = os.environ.get("IG_GRAPH_VERSION", "v23.0")
TOKEN_NAME = "instagram.token.json"
REFRESH_AFTER_DAYS = 50
POLL_SECONDS, POLL_MAX = 5, 120  # at most 10 minutes of processing


def _requests():
    import requests
    return requests


def _check(resp) -> dict:
    try:
        data = resp.json()
    except ValueError:
        raise PublishError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    if resp.status_code >= 400 or "error" in data:
        err = data.get("error", {})
        raise PublishError(f"HTTP {resp.status_code}: {err.get('message', data)}"
                           f" (code {err.get('code')}, subcode {err.get('error_subcode')})")
    return data


def api(method: str, path: str, token: str, mode: str = "unified", **params) -> dict:
    url = f"{HOSTS[mode]}/{VERSION}/{path.lstrip('/')}"
    params["access_token"] = token
    r = _requests().request(method, url, params=params if method == "GET" else None,
                            data=params if method != "GET" else None, timeout=60)
    return _check(r)


# ------------------------------------------------------------------------ token
def _identify(token: str) -> dict:
    """Detects the token type and finds the linked Instagram account."""
    errors = []
    try:  # Unified login: system-user token, assigned account
        r = api("GET", "me/assigned_instagram_accounts", token, "unified", fields="id,username")
        accounts = r.get("data", [])
        if accounts:
            acc = accounts[0]
            if len(accounts) > 1:
                log(P, f"{len(accounts)} assigned accounts, using @{acc.get('username')}.")
            return {"mode": "unified", "user_id": acc["id"], "username": acc.get("username")}
        errors.append("unified: no Instagram account assigned to the token")
    except PublishError as e:
        errors.append(f"unified: {e}")
    try:  # legacy Instagram login
        me = api("GET", "me", token, "instagram", fields="user_id,username")
        return {"mode": "instagram", "user_id": me["user_id"], "username": me.get("username")}
    except PublishError as e:
        errors.append(f"instagram: {e}")
    raise PublishError("Token not recognized.\n  " + "\n  ".join(errors))


def set_token(token: str) -> dict:
    data = {"access_token": token, **_identify(token), "obtained_at": now_iso()}
    save_secret(TOKEN_NAME, data)
    log(P, f"Token saved for @{data['username']} (id {data['user_id']}, mode {data['mode']}).")
    return data


def get_token() -> dict:
    tok = load_secret(TOKEN_NAME)
    tok.setdefault("mode", "instagram")  # tokens saved before the unified mode was added
    if tok["mode"] != "instagram":
        return tok  # system-user token: never expires
    age = datetime.now(timezone.utc) - datetime.fromisoformat(tok["obtained_at"])
    if age.days >= REFRESH_AFTER_DAYS:
        log(P, "Renewing the long-lived token…")
        r = _check(_requests().get(f"{HOSTS['instagram']}/refresh_access_token", timeout=60, params={
            "grant_type": "ig_refresh_token", "access_token": tok["access_token"]}))
        tok.update(access_token=r["access_token"], obtained_at=now_iso())
        save_secret(TOKEN_NAME, tok)
    return tok


# ------------------------------------------------------------------- publishing
def publish(video: Path, meta: dict, *, private: bool = False, dry_run: bool = False,
            **_ignored) -> dict:
    if private:
        raise PublishError("Instagram has no private publishing: skipped in test mode.")
    pm = platform_meta(meta, P)
    params = {"media_type": "REELS", "upload_type": "resumable",
              "caption": caption_for(meta, P),
              "share_to_feed": "true" if pm.get("share_to_feed", True) else "false"}
    cover = resolve_cover(video, meta, P)
    if cover["url"]:
        params["cover_url"] = cover["url"]              # exact image, through a public URL
    else:
        params["thumb_offset"] = str(cover["time_ms"])  # otherwise the video frame at that time
        if cover["from_json"] and pm.get("cover_time_ms", meta.get("cover_time_ms")) is None:
            log(P, "The JSON image cannot be sent without a public URL: using the frame at "
                   f"{cover['time_ms']} ms. Add \"cover_time_ms\" to make them match.")
    if dry_run:
        log(P, "Dry run:\n" + json.dumps(params, ensure_ascii=False, indent=2))
        return {}

    tok = get_token()
    token, uid, mode = tok["access_token"], tok["user_id"], tok["mode"]
    size = video.stat().st_size

    # 1. Container
    c = api("POST", f"{uid}/media", token, mode, **params)
    cid = c["id"]
    upload_uri = c.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{VERSION}/{cid}"
    log(P, f"Container {cid} created, uploading {size / 1e6:.1f} MB…")

    # 2. File upload (resumable upload, in one go)
    with video.open("rb") as fh:
        r = _requests().post(upload_uri, data=fh, timeout=600, headers={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)})
    _check(r)

    # 3. Wait for processing
    for _ in range(POLL_MAX):
        st = api("GET", cid, token, mode, fields="status_code,status")
        code = st.get("status_code")
        if code == "FINISHED":
            break
        if code in {"ERROR", "EXPIRED"}:
            raise PublishError(f"Instagram processing failed: {st.get('status')}")
        time.sleep(POLL_SECONDS)
    else:
        raise PublishError("Instagram processing took too long (10 min).")

    # 4. Publish
    media_id = api("POST", f"{uid}/media_publish", token, mode, creation_id=cid)["id"]
    link = api("GET", media_id, token, mode, fields="permalink").get("permalink")
    log(P, f"Published: {link}")
    return {"id": media_id, "url": link}


# --------------------------------------------------------------------------- CLI
def main() -> None:
    ap = argparse.ArgumentParser(description="Instagram Reels publishing")
    ap.add_argument("video", nargs="?", type=Path)
    ap.add_argument("--meta", type=Path)
    ap.add_argument("--set-token", metavar="TOKEN")
    ap.add_argument("--whoami", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    try:
        if a.set_token:
            set_token(a.set_token.strip())
            return
        if a.whoami:
            t = get_token()
            info = api("GET", t["user_id"], t["access_token"], t["mode"],
                       fields="username,media_count" + (",account_type" if t["mode"] == "instagram" else ""))
            log(P, f"mode {t['mode']} | " + json.dumps(info, ensure_ascii=False))
            return
        if not a.video:
            ap.error("video path required")
        video = video_for(a.video)
        prev = published_entry(video, P)
        if prev and not a.force and not a.dry_run:
            log(P, f"Already published ({prev.get('url') or 'manually'}). Use --force to upload again.")
            return
        res = publish(video, load_meta(video, a.meta), dry_run=a.dry_run)
        if res:
            record(video, P, res)
    except PublishError as e:
        die(f"[{P}] ERROR: {e}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted (Ctrl+C).")
        raise SystemExit(130)
