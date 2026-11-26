# Statistics and comments

Every 6 hours the publishing server collects the YouTube and TikTok counters, keeps a dated history
and builds a summary page, `stats/index.html`: totals, a table of the videos with their 24-hour
change and views trend, and the YouTube comments, those waiting for an answer first. YouTube
comments can be answered from the PC.

## Viewing

From the PC:

```powershell
powershell -ExecutionPolicy Bypass -File tools\deploy\open_stats.ps1            # last page
powershell -ExecutionPolicy Bypass -File tools\deploy\open_stats.ps1 -Refresh   # collect first
```

The page is copied to `%TEMP%` and opened in the browser. It is self-contained (no script, no
external resource) and nothing is exposed on the network.

## Replying to YouTube comments

```powershell
powershell -ExecutionPolicy Bypass -File tools\deploy\reply_comment.ps1                       # walk through pending comments
powershell -ExecutionPolicy Bypass -File tools\deploy\reply_comment.ps1 -List                 # list them with their id
powershell -ExecutionPolicy Bypass -File tools\deploy\reply_comment.ps1 -Id <id> -Text "Thanks!"
```

- **Interactive walk**: each pending comment is shown; type the reply (Enter skips, `q` quits) and
  confirm before it is posted publicly.
- **One comment**: the id is shown on the statistics page, with the ready-to-copy command. The text
  is sent as UTF-8, so accents and emoji are kept.
- The reply is posted with the YouTube Data API (`comments.insert`, scope `youtube.force-ssl`,
  already granted); the comment is then marked as answered and the page is rebuilt.
- On the server directly: `.venv/bin/python tools/stats/reply.py --list | --interactive | <id> "text"`.

TikTok comments cannot be read or answered: the public API gives no access to them.

## What is collected

| Platform | Counters | Comments | Prerequisite |
|---|---|---|---|
| YouTube | views, likes, comment count (no shares through the API) | text, author, date, likes, and **answered or not**; replies from the PC | none: current token (`youtube.readonly`, `youtube.force-ssl`) |
| TikTok | views, likes, comments, shares | count only (contents not available through the public API) | **Display API** product and `video.list` scope (see below) |

A YouTube comment is "answered" when the account replied to it or wrote it. The "Open on YouTube"
link opens the video on that comment. TikTok counters can lag by several hours.

Matching with the `videos/` folders: YouTube by the id saved in `published.json`; TikTok by id when
known, otherwise by the start of the caption (in draft mode, TikTok does not return the id of the
final video).

## Enabling TikTok statistics (once)

1. developers.tiktok.com → the app → **Add products** → **Display API**.
2. Check that the `video.list` scope appears in Scopes (add it to the Sandbox too if needed).
3. In `.env`: `VS_TIKTOK_SCOPES=user.info.basic,video.publish,video.upload,video.list`.
4. Deploy, then authorize again:
   `tools\deploy\deploy_linux.ps1 -SkipTests`, then `tools\deploy\auth_tunnel.ps1 tiktok`.

Until then, the page shows "video.list scope missing" and only YouTube.

## Files (on the server, `stats/`, excluded from Git)

| File | Content |
|---|---|
| `history.jsonl` | one line per video and per collection (timestamp, counters): the basis of the changes |
| `latest.json` | last full state: videos, counters, comments, errors |
| `index.html` | the summary page |

Server commands: `.venv/bin/python tools/stats/collect.py` (collect + page), `--render` (page only,
no network call), `--no-comments`. Timer logs: `journalctl --user -u video-studio-stats -n 20`.

## Quotas

A YouTube collection costs a few units of the daily quota (10,000): 1 per page of 50 videos and
1 per page of 100 comments. A reply costs 50 units. Every 6 hours, this is negligible.
