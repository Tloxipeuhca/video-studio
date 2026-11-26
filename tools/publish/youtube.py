"""YouTube publishing with the YouTube Data API v3.

    python tools/publish/youtube.py --auth-only
    python tools/publish/youtube.py VIDEO.mp4 [--privacy private] [--publish-at ISO] [--dry-run] [--force]
"""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

from common import (video_for, PublishError, die, headless, load_meta, load_secret, log, platform_meta,
                    published_entry, record, resolve_cover, save_secret, LOOPBACK, free_port,
                    setup_auth_browser)

P = "youtube"
CLIENT_NAME = "youtube.client_secret.json"  # gopass: youtube/client_secret ; files: secrets/client_secret*.json
TOKEN_NAME = "youtube.token.json"          # gopass: youtube/token


def client_config() -> dict:
    """OAuth client of type "Desktop app", downloaded from Google Cloud."""
    return load_secret(CLIENT_NAME)


# upload: publish | readonly: statistics | force-ssl: read and answer comments
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
# Local ports for the authorization redirect: fixed, and accepted by Chrome
# (a random port may hit a blocked one, e.g. 6666 -> ERR_UNSAFE_PORT)
AUTH_PORTS = (47811, 47812, 47813, 47814, 47815)
RETRIABLE_STATUS = {500, 502, 503, 504}
MAX_RETRIES = 8
CHUNK_SIZE = 8 * 1024 * 1024


# --------------------------------------------------------------------------- auth
def get_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    info = load_secret(TOKEN_NAME, required=False)
    if info:
        creds = Credentials.from_authorized_user_info(info, SCOPES)
        if not set(SCOPES).issubset(set(creds.scopes or [])):
            log(P, "New permissions required: authorizing again.")
            creds = None
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_secret(TOKEN_NAME, json.loads(creds.to_json()))
            return creds
        except Exception as exc:
            log(P, f"Token refresh failed ({exc}): new authorization.")
    flow = InstalledAppFlow.from_client_config(client_config(), SCOPES)
    setup_auth_browser()
    port = free_port(AUTH_PORTS, P)
    if headless():
        log(P, f"Server without a display: open the address below on the PC, through the SSH tunnel "
               f"of port {port} (tools\\deploy\\auth_tunnel.ps1).")
    try:
        creds = flow.run_local_server(host=LOOPBACK, port=port, open_browser=not headless(),
                                      prompt="select_account consent", access_type="offline")
    except Exception as exc:
        if "access_denied" in str(exc):
            raise PublishError(
                "Authorization denied by Google (access_denied). Common causes: clicking "
                "\"Back to safety\" or \"Cancel\", wrong account selected, account missing from the "
                "test users (Google Auth Platform > Audience).") from exc
        raise
    save_secret(TOKEN_NAME, json.loads(creds.to_json()))
    log(P, "Token saved.")
    return creds


def service():
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=get_credentials(), cache_discovery=False)


# ------------------------------------------------------------------------- upload
def _resumable(request) -> dict:
    from googleapiclient.errors import HttpError

    response, retry = None, 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                log(P, f"Upload: {int(status.progress() * 100)} %")
            continue
        except HttpError as err:
            if err.resp.status not in RETRIABLE_STATUS:
                raise PublishError(f"HTTP {err.resp.status}: {err}") from err
            error = f"HTTP {err.resp.status}"
        except (ConnectionError, TimeoutError, OSError) as err:
            error = repr(err)
        retry += 1
        if retry > MAX_RETRIES:
            raise PublishError(f"Giving up after {MAX_RETRIES} attempts ({error}).")
        wait = min(2 ** retry, 64) + random.random()
        log(P, f"Temporary error ({error}), retrying in {wait:.0f} s…")
        time.sleep(wait)
    return response


def _thumbnail(svc, video_id: str, thumb: Path) -> None:
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload
    try:
        svc.thumbnails().set(videoId=video_id,
                             media_body=MediaFileUpload(str(thumb), mimetype="image/jpeg")).execute()
        log(P, "Thumbnail applied.")
    except HttpError as err:
        log(P, f"Thumbnail not applied (HTTP {err.resp.status}), continuing without it.")


def publish(video: Path, meta: dict, *, private: bool = False, publish_at: str | None = None,
            dry_run: bool = False) -> dict:
    pm = platform_meta(meta, P)
    title = pm.get("title") or meta.get("title")
    if not title or len(title) > 100:
        raise PublishError("Title missing or longer than 100 characters.")
    lang = pm.get("language", meta.get("language", "en"))
    status = {"privacyStatus": "private" if private else pm.get("privacy", "public"),
              "selfDeclaredMadeForKids": False, "containsSyntheticMedia": False}
    if publish_at:
        status.update(privacyStatus="private", publishAt=publish_at)
    body = {
        "snippet": {"title": title,
                    "description": pm.get("description") or meta.get("description", ""),
                    "tags": pm.get("tags") or meta.get("tags", []),
                    "categoryId": str(pm.get("categoryId", "22")),
                    "defaultLanguage": lang, "defaultAudioLanguage": lang},
        "status": status,
    }
    cover = resolve_cover(video, meta, P)
    if dry_run:
        log(P, "Dry run:\n" + json.dumps(body, ensure_ascii=False, indent=2))
        src = "JSON" if cover["from_json"] else f"frame extracted at {cover['time_ms']} ms"
        log(P, f"Thumbnail: {cover['image'] or 'none'} ({src})")
        return {}

    from googleapiclient.http import MediaFileUpload
    svc = service()
    media = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=CHUNK_SIZE, resumable=True)
    log(P, f"Uploading {video.name} ({video.stat().st_size / 1e6:.1f} MB)…")
    resp = _resumable(svc.videos().insert(part="snippet,status", body=body, media_body=media))
    vid = resp["id"]
    log(P, f"Published: https://www.youtube.com/watch?v={vid}")
    if cover["image"]:
        _thumbnail(svc, vid, cover["image"])
    return {"id": vid, "url": f"https://www.youtube.com/watch?v={vid}",
            "privacy": status["privacyStatus"], "publishAt": publish_at}


# --------------------------------------------------------------------------- CLI
def main() -> None:
    ap = argparse.ArgumentParser(description="YouTube publishing")
    ap.add_argument("video", nargs="?", type=Path)
    ap.add_argument("--meta", type=Path)
    ap.add_argument("--privacy", choices=["public", "unlisted", "private"])
    ap.add_argument("--publish-at")
    ap.add_argument("--auth-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    try:
        if a.auth_only:
            get_credentials()
            log(P, "Authorization OK.")
            return
        if not a.video:
            ap.error("video path required (or --auth-only)")
        video = video_for(a.video)
        prev = published_entry(video, P)
        if prev and not a.force and not a.dry_run:
            log(P, f"Already published ({prev.get('url') or 'manually'}). Use --force to upload again.")
            return
        meta = load_meta(video, a.meta)
        if a.privacy:
            meta.setdefault(P, {})["privacy"] = a.privacy
        res = publish(video, meta, publish_at=a.publish_at, dry_run=a.dry_run)
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
