# video-studio

Automated video editing (FFmpeg + Python) and automatic, optionally scheduled, publishing to
YouTube and TikTok from a Linux server — with statistics, and replies to YouTube comments, from a
single place.

It works with any kind of video: any source (camera, screen recording, phone, existing footage),
any format (vertical or horizontal) and any length accepted by the platforms. Each video has its own
editing script, so the pipeline is not tied to a type of content.

Publishing to **Instagram** is also implemented (`tools/publish/instagram.py`). It is not
enabled by default and is currently untested: the account used to test it was suspended by Meta.

## Architecture

```
Editing PC (Windows or Linux)                   Publishing server (Linux, always on)
  videos/<folder>/montage/*.py  (FFmpeg)
  output/  +  publish.json   ──push_video.ps1──►  videos/<folder>/
                                                 systemd timer (15 min): run.py --scan videos --due
                                                 secrets in gopass ──► YouTube / TikTok
                                                 systemd timer (6 h): statistics ──► stats/index.html
  open_stats.ps1 / reply_comment.ps1  ◄──ssh──── page, YouTube comments to answer
```

- **Editing**: any machine with FFmpeg and Python. Timings are similar on Windows and Linux
  (16.6 s vs 17.9 s for the reference edit, see `tools/bench/`).
- **Publishing**: only on the server, where the secrets live (gopass). No secret in clear text on disk.
- **Personal configuration** (server, paths, vault, Chrome profile): a `.env` file excluded from Git,
  with the `.env.example` template; see [docs/configuration.md](docs/configuration.md).

## Layout

```
video-studio/
├─ .env.example         configuration template (copy to .env, excluded from Git)
├─ requirements.txt     Python dependencies (requirements-dev.txt: tests)
├─ docs/                documentation
├─ tools/
│  ├─ publish/          YouTube / TikTok publishing, secret storage, self-test
│  ├─ stats/            statistics collection, summary page, replies to comments
│  ├─ deploy/           server deployment, video upload, authorization tunnel, systemd units
│  ├─ secrets/          initial copy of the secrets into gopass
│  └─ bench/            editing performance test
├─ tests/               unit tests (no network, fake gopass)
├─ assets/              emoji and shared graphic elements
└─ videos/
   └─ YYYY-MM-DD_topic/   (personal content, not versioned)
      ├─ montage/       editing script of the video
      ├─ source/        raw capture
      ├─ output/        final video, thumbnail
      ├─ publish.json   publishing metadata (and optional "schedule")
      └─ published.json publishing log (kept by the server)
```

## New video

1. Create `videos/YYYY-MM-DD_topic/` with `source/`, `montage/`, `output/`.
2. Render the video into `output/` with an FFmpeg/Python script in `montage/`.
3. Write `publish.json` (see [docs/metadata.md](docs/metadata.md)).
4. Send it to the server, with or without a publishing time:

   ```powershell
   powershell -ExecutionPolicy Bypass -File tools\deploy\push_video.ps1 videos\<folder> -Schedule "2026-11-28T18:00"
   ```

   Without `-Schedule`, nothing is published automatically: run `run.py <folder>` on the server.
   TikTok (`inbox` mode) receives a draft, to confirm in the app.

## Documentation

| Document | Content |
|---|---|
| [docs/configuration.md](docs/configuration.md) | The `.env` file: every setting, expected gopass entries |
| [docs/workstation.md](docs/workstation.md) | Editing PC: prerequisites, `.venv`, `.env` |
| [docs/server.md](docs/server.md) | Publishing server: setup, scheduling, re-authorization, tests |
| [docs/platforms.md](docs/platforms.md) | Creating the YouTube and TikTok apps and getting the credentials |
| [docs/metadata.md](docs/metadata.md) | `publish.json` format, scheduling, thumbnail rules |
| [docs/statistics.md](docs/statistics.md) | YouTube and TikTok statistics, summary page, replying to comments |
| [tools/publish/README.md](tools/publish/README.md) | Publishing commands and options |
