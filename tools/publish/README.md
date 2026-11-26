# tools/publish

Publishing to YouTube and TikTok. An Instagram module is also implemented but untested: the
account used to test it was suspended by Meta; it is not in the default platforms. These commands
run **on the publishing server**, in `VS_SERVER_DIR`, where the secrets are: see
[docs/server.md](../../docs/server.md) and [docs/configuration.md](../../docs/configuration.md).
Metadata format: [docs/metadata.md](../../docs/metadata.md).

## Commands (on the server, from the project root)

    .venv/bin/python tools/publish/run.py videos/<folder>                # a video folder (or its publish.json, or the .mp4)
    .venv/bin/python tools/publish/run.py --scan videos                  # every video not yet published
    .venv/bin/python tools/publish/run.py --scan videos --due            # videos whose "schedule" has passed (systemd timer)
    .venv/bin/python tools/publish/run.py <folder> --platforms youtube   # a single platform (default: youtube,tiktok)
    .venv/bin/python tools/publish/run.py <folder> --test                # YouTube private, TikTok SELF_ONLY, log untouched
    .venv/bin/python tools/publish/run.py <folder> --dry-run             # show without uploading
    .venv/bin/python tools/publish/run.py <folder> --force               # ignore published.json
    .venv/bin/python tools/publish/selftest.py [--online]                # self-test of the publishing machine

Each module also runs on its own: `youtube.py`, `tiktok.py`, `instagram.py` (`--help`).
Re-authorization from the PC (the server has no display): `tools\deploy\auth_tunnel.ps1 youtube|tiktok`.

| File | Role |
|---|---|
| `run.py` | Multi-platform launcher, `--due` filter, lock against simultaneous runs |
| `common.py` | Metadata, publishing log, scheduling, cover image, authorization browser |
| `settings.py` | Reads the `VS_*` configuration (environment, then `.env`) |
| `secrets_store.py` | Secrets: gopass (recommended) or `secrets/` files |
| `selftest.py` | Self-test: tools, configuration, vault, secrets present, tokens (`--online`) |
| `youtube.py` | YouTube Data API v3 (desktop-app OAuth) |
| `tiktok.py` | TikTok Content Posting API (direct or inbox) |
| `instagram.py` | Instagram API — implemented, untested, opt-in with `--platforms` |

Statistics and replies to comments: [tools/stats](../stats) and [docs/statistics.md](../../docs/statistics.md).
