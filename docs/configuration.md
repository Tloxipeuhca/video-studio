# Machine configuration (.env)

Everything specific to an installation (server, paths, secret vault, Chrome profile) lives in a
**`.env`** file at the project root. It is **excluded from Git**: the repository only holds generic
code and the **`.env.example`** template.

```powershell
Copy-Item .env.example .env     # then edit .env
```

The same `.env` serves the editing PC and the server: `tools\deploy\deploy_linux.ps1` copies it to
the server (mode `600`). Any setting can also be defined in the environment, which takes precedence
over `.env` (handy for a one-off test).

## Settings

| Setting | Used by | Purpose | Example |
|---|---|---|---|
| `VS_SERVER` | PC: `tools\deploy\` scripts, `push_secrets.py`, benchmark | SSH login of the publishing server | `user@192.168.1.10` |
| `VS_SERVER_DIR` | PC: deployment; server: systemd timers | Project folder on the server | `/srv/video-studio` |
| `VS_SECRETS_BACKEND` | where publishing happens (server) | `gopass` (recommended) or `files` (`secrets/` folder, clear text) | `gopass` |
| `VS_GOPASS_PREFIX` | server, `push_secrets.py` | Entry prefix: `<vault mount>/<folder>` | `vault-low/video-studio` |
| `VS_GOPASS_CMD` | server, `push_secrets.py` | Command used instead of `gopass`, e.g. a wrapper selecting the vault profile. Empty: `gopass` from PATH | `bash /opt/vault/vault-ctl.sh gopass` |
| `VS_TIKTOK_SCOPES` | server (TikTok authorization) | Permissions requested from TikTok; add `video.list` for statistics ([statistics.md](statistics.md)) | `user.info.basic,video.publish,video.upload` |
| `VS_CHROME_PATH` | PC (OAuth authorizations) | Chrome used for the authorization pages | `C:\Program Files\Google\Chrome\Application\chrome.exe` |
| `VS_CHROME_PROFILE` | PC (OAuth authorizations) | Chrome profile signed in to the project's Google account (`chrome://version`) | `Profile 2` |

Format: `KEY=value`, one per line; `#` for comments; optional quotes; no variable expansion
(backslashes in Windows paths are kept as they are).

## Expected gopass entries

Under `VS_GOPASS_PREFIX`, each entry holds the compact JSON of one secret, read and written with
`gopass cat` (stdin = `/dev/null` to read, otherwise gopass assumes a write).

| Entry | Content | Rewritten by the code |
|---|---|---|
| `<prefix>/youtube/client_secret` | "Desktop app" OAuth client (Google Cloud) | no |
| `<prefix>/youtube/token` | YouTube token (with refresh token) | yes, on every refresh |
| `<prefix>/tiktok/app` | `{"client_key": "...", "client_secret": "..."}` | no |
| `<prefix>/tiktok/token` | TikTok tokens and expiry dates | yes, every 24 h |

Initial copy from a `secrets/` folder: `py tools\secrets\push_secrets.py --apply`.
Check on the server: `.venv/bin/python tools/publish/selftest.py --online`.

## Never versioned

`.env`, `secrets/`, `private/` (brand assets, legal pages), `.venv/`, the video projects
(`videos/`), collected statistics (`stats/`), benchmark results and the
`.publish.lock` lock (see `.gitignore`).
