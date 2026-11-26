# Linux publishing server

Videos are edited on Windows **or** Linux (same scripts, similar timings: 16.6 s vs 17.9 s for the
reference edit). **Publishing** always happens from the Linux server (`VS_SERVER`, always on), with the
secrets in **gopass**. No secret in clear text on disk. Every installation-specific value is in
`.env`: see [configuration.md](configuration.md).

```
Windows PC                                   Linux server (VS_SERVER)
  FFmpeg editing ──► push_video.ps1 ──ssh──►  $VS_SERVER_DIR/videos/<folder>/
                                              systemd timer (15 min): run.py --scan videos --due
  (or edit directly on Linux)                  └─► YouTube / TikTok, tokens read from and written to gopass
```

## 1. gopass entries

Prefix: `VS_GOPASS_PREFIX` from `.env` (e.g. `vault-low/video-studio`). Each entry holds the compact
JSON of the original file, written with `gopass cat`.

| gopass entry | Original file (PC `secrets\`) | Rewritten automatically |
|---|---|---|
| `<prefix>/youtube/client_secret` | `client_secret_*.apps.googleusercontent.com.json` | no |
| `<prefix>/youtube/token` | `youtube.token.json` | yes (refresh) |
| `<prefix>/tiktok/app` | `tiktok_app.json` | no |
| `<prefix>/tiktok/token` | `tiktok.token.json` | yes (every 24 h) |

Manual read: `gopass cat <prefix>/tiktok/app </dev/null`. The `</dev/null` is required outside a
terminal, otherwise `gopass cat` waits for a write.

## 2. Setup (once)

From the project root on the PC:

| Step | Command | Expected |
|---|---|---|
| 0. Configuration | `Copy-Item .env.example .env`, then edit | see [configuration.md](configuration.md) |
| 1. SSH key to the server (no password) | `ssh $VS_SERVER hostname` | answers without asking for a password |
| 2. Check the vault mount name | `ssh $VS_SERVER "gopass mounts"` | the mount of `VS_GOPASS_PREFIX` is listed |
| 3. Deploy code + `.venv` + tests | `powershell -ExecutionPolicy Bypass -File tools\deploy\deploy_linux.ps1` | all tests passed |
| 4. Copy the secrets (dry run) | `py tools\secrets\push_secrets.py` | 4 entries "would be copied" |
| 5. Copy the secrets | `py tools\secrets\push_secrets.py --apply` | 4 × "copied and read back identical" |
| 6. Server self-test | `ssh $VS_SERVER "cd $VS_SERVER_DIR && .venv/bin/python tools/publish/selftest.py --online"` | all OK, YouTube and TikTok accounts shown |
| 7. Self-test from systemd | `ssh $VS_SERVER "cd $VS_SERVER_DIR && systemd-run --user --wait -P .venv/bin/python tools/publish/selftest.py"` | all OK (vault readable without a terminal) |
| 8. Real test upload | `ssh $VS_SERVER "cd $VS_SERVER_DIR && .venv/bin/python tools/publish/run.py videos/<folder> --test --force"` | private YouTube video + SELF_ONLY TikTok draft |
| 9. Enable the timers | `powershell -ExecutionPolicy Bypass -File tools\deploy\deploy_linux.ps1 -InstallTimer`, then `ssh -t $VS_SERVER "sudo loginctl enable-linger \$USER"` | timers listed |
| 10. Delete the clear-text secrets on the PC | by hand, once 6 to 8 are validated: `secrets\` | — |

Before step 8, send the video with `push_video.ps1 videos\<folder>`. If the video was already
published from another machine, `push_video.ps1` also sends its `published.json` the first time, so
that the server does not publish it again.

## 3. Daily use

```powershell
# Edited on the PC -> sent to the server, scheduled publishing (server local time)
powershell -ExecutionPolicy Bypass -File tools\deploy\push_video.ps1 videos\2026-11-28_xxx -Schedule "2026-11-28T18:00"
```

- `"schedule"` in `publish.json`: the timer publishes at that time (within 15 min).
  **Without `schedule`, nothing is published automatically**: only by hand with `run.py`.
- TikTok in `inbox` mode: at the scheduled time the video lands as a **draft** in the app; it only
  becomes public once confirmed in TikTok. YouTube publishes directly.
- Statistics and comments: `tools\deploy\open_stats.ps1` and `tools\deploy\reply_comment.ps1`
  (see [statistics.md](statistics.md)).
- Timer logs: `ssh $VS_SERVER "journalctl --user -u video-studio-publish -n 50"`.
- Code update: run `deploy_linux.ps1` again. It also replaces the server `.env` with the PC one
  (single source), without touching the videos, `published.json` or gopass.

## 4. Re-authorizing YouTube or TikTok

The server has no display: the SSH tunnel brings the authorization page to the PC.

```powershell
powershell -ExecutionPolicy Bypass -File tools\deploy\auth_tunnel.ps1 youtube   # or tiktok
```

Open the printed address in Chrome, with the `VS_CHROME_PROFILE` profile (the project's Google
account). The new token is written straight into gopass on the server. Needed when
`selftest.py --online` reports a rejected token, when the TikTok refresh token expires (date shown
by `selftest.py`), or after adding a scope.

## 5. Tests

| Test | Where | Command |
|---|---|---|
| Unit tests (fake gopass, no network) | PC or server | `python -m pytest` |
| Machine self-test (tools, vault, secrets) | server | `python tools/publish/selftest.py` |
| Valid tokens (read-only) | server | `python tools/publish/selftest.py --online` |
| Publishing dry run | server | `python tools/publish/run.py <folder> --dry-run` |
| Real private upload | server | `python tools/publish/run.py <folder> --test --force` |
