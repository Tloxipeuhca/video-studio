# Publishing metadata (`publish.json`)

Each video folder has a `publish.json`. Paths are relative to that folder.

```json
{
  "video": "output/harbour_sunset.mp4",
  "title": "Sunset over the harbour 🌅",
  "description": "Ten seconds of calm before the evening rush.\n\n#sunset #harbour",
  "tags": ["sunset", "harbour", "timelapse"],
  "language": "en",
  "thumbnail": "output/thumbnail.jpg",
  "cover_time_ms": 4000,
  "caption": "Sunset over the harbour 🌅 Ten seconds of calm",
  "hashtags": ["#sunset", "#harbour", "#timelapse"],
  "schedule": "2026-11-28T18:00",
  "youtube":   { "categoryId": "22", "privacy": "public" },
  "tiktok":    { "extra_hashtags": ["#fyp"], "mode": "inbox", "privacy": "SELF_ONLY" }
}
```

## Common fields

| Field | Required | Purpose |
|---|---|---|
| `video` | Yes | Path of the final video |
| `title` | Yes (YouTube) | Title, 100 characters maximum |
| `description` | No | YouTube description |
| `tags` | No | YouTube keywords |
| `language` | No | Language (default `en`) |
| `caption` | No | TikTok (and Instagram) caption (default: `title`) |
| `hashtags` | No | Appended to the caption on TikTok (and Instagram) |
| `thumbnail` | No | Reference cover image |
| `cover_time_ms` | No | Position in the video used when an image cannot be sent |
| `cover_url` | No | Public image URL (the only way to send it to Instagram) |
| `schedule` | No | Automatic publishing time on the server, ISO 8601: `2026-11-28T18:00` (server local time) or `2026-11-28T18:00+01:00`. Without it, manual publishing only. Written by `push_video.ps1 -Schedule` |

Each `youtube`, `tiktok` (and `instagram`) block can override these fields for its platform, and add:

| Platform | Own fields |
|---|---|
| YouTube | `categoryId` (YouTube category id, default `22` = People & Blogs), `privacy` (`public`, `unlisted`, `private`) |
| TikTok | `extra_hashtags`, `mode` (`inbox` recommended before the audit: draft confirmed in the app; `direct`: private account required before the audit), `privacy`, `disable_comment`, `disable_duet`, `disable_stitch` |
| Instagram | `extra_hashtags`, `share_to_feed` |

## Cover image

Without `thumbnail` or `cover_time_ms`: frame at 4 s (capped to the duration), extracted with FFmpeg
into `output/<video>.cover.jpg`.

| Platform | What is sent |
|---|---|
| YouTube | the `thumbnail` file, otherwise the extracted frame |
| TikTok | the `cover_time_ms` position (the API does not accept an image) |
| Instagram | `cover_url` if present, otherwise the `cover_time_ms` position |

If the thumbnail is a frame taken from the video, also set `cover_time_ms` so that every platform
shows the same picture.

## `published.json` log

Filled by the scripts after each upload (id, link, date). A platform already present is never
published again, unless `--force` is used. A manual upload is recorded by hand:
`"youtube": { "manual": true, "uploadedAt": "2026-11-25" }`.

## Scheduling

The server timer (every 15 min) publishes the videos whose `schedule` has passed and that are not
yet in `published.json` for every platform. Accuracy: about 15 min. YouTube publishes directly;
TikTok in `inbox` mode drops a draft at the scheduled time, public only once confirmed in the app.
To move it: change `schedule` and send again with `push_video.ps1`; to cancel: remove the field.
