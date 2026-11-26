"""Statistics summary page (self-contained HTML: no script, font or image loaded from outside)."""
from __future__ import annotations

from datetime import datetime, timedelta
from html import escape

PLATFORM = {"youtube": "YouTube", "tiktok": "TikTok"}


def fmt(n) -> str:
    if n is None:
        return "—"
    return f"{n:,}"


def fmt_delta(n) -> str:
    if not n:
        return ""
    return f'<span class="delta">+{fmt(n)}</span>' if n > 0 else f'<span class="delta neg">{fmt(n)}</span>'


def local_dt(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return iso or ""


def series(history: list[dict], platform: str, vid: str) -> list[tuple[datetime, dict]]:
    pts = [(datetime.fromisoformat(h["ts"]), h) for h in history if h["platform"] == platform and h["id"] == vid]
    return sorted(pts, key=lambda p: p[0])


def delta_24h(points: list[tuple[datetime, dict]], field: str):
    """24-hour change: latest sample minus the most recent sample that is at least 24 hours old."""
    if len(points) < 2:
        return None
    last_ts, last = points[-1]
    older = [h for ts, h in points if ts <= last_ts - timedelta(hours=24)]
    base = older[-1] if older else points[0][1]
    if base.get(field) is None or last.get(field) is None:
        return None
    return last[field] - base[field]


def sparkline(points: list[tuple[datetime, dict]], w: int = 120, h: int = 28) -> str:
    vals = [p[1]["views"] for p in points[-40:]]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    step = w / (len(vals) - 1)
    pts = " ".join(f"{i * step:.1f},{h - 2 - (v - lo) / span * (h - 4):.1f}" for i, v in enumerate(vals))
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" aria-label="views trend">'
            f'<polyline points="{pts}" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>')


def render(state: dict, history: list[dict]) -> str:
    videos = state.get("videos", [])
    comments = state.get("comments", [])
    yt_titles = {v["id"]: v["title"] for v in videos if v["platform"] == "youtube"}

    # --- totals per platform
    tiles = []
    for plat in ("youtube", "tiktok"):
        vs = [v for v in videos if v["platform"] == plat]
        if not vs:
            continue
        d = [delta_24h(series(history, plat, v["id"]), "views") for v in vs]
        d24 = sum(x for x in d if x)
        tiles.append(f'<div class="tile"><div class="label">{PLATFORM[plat]}</div>'
                     f'<div class="value">{fmt(sum(v["views"] for v in vs))}</div>'
                     f'<div class="sub">views · {len(vs)} video(s) · {fmt(sum(v["likes"] for v in vs))} likes'
                     f'{" · " + fmt_delta(d24) + " in 24 h" if d24 else ""}</div></div>')
    todo = [c for c in comments if not c["answered"]]
    tiles.append(f'<div class="tile"><div class="label">YouTube comments to answer</div>'
                 f'<div class="value">{len(todo)}</div><div class="sub">out of {len(comments)} collected</div></div>')

    # --- videos table
    rows = []
    for v in sorted(videos, key=lambda v: v.get("published") or "", reverse=True):
        pts = series(history, v["platform"], v["id"])
        title = escape(v["title"] or "(untitled)")
        link = f'<a href="{escape(v["url"])}">{title}</a>' if v.get("url") else title
        folder = f'<div class="muted">{escape(v["folder"])}</div>' if v.get("folder") else ""
        priv = f' <span class="badge">{escape(v["privacy"])}</span>' if v.get("privacy") not in (None, "public") else ""
        rows.append(
            f'<tr><td><span class="plat {v["platform"]}">{PLATFORM[v["platform"]]}</span></td>'
            f'<td>{link}{priv}{folder}</td><td class="muted">{local_dt(v.get("published"))}</td>'
            f'<td class="num">{fmt(v["views"])} {fmt_delta(delta_24h(pts, "views"))}</td>'
            f'<td class="num">{fmt(v["likes"])}</td><td class="num">{fmt(v["comments"])}</td>'
            f'<td class="num">{fmt(v["shares"])}</td><td>{sparkline(pts)}</td></tr>')

    # --- comments: pending first (newest first), then the 20 latest answered ones
    citems = []
    ordered = sorted(todo, key=lambda c: c.get("published") or "", reverse=True) + \
        sorted([c for c in comments if c["answered"]], key=lambda c: c.get("published") or "", reverse=True)[:20]
    for c in ordered:
        label = '<span class="badge ok">answered</span>' if c["answered"] else '<span class="badge todo">to answer</span>'
        cmd = "" if c["answered"] else (
            f'<code class="cmd">tools\\deploy\\reply_comment.ps1 -Id {escape(c["id"])} -Text "..."</code>')
        citems.append(
            f'<li class="{"done" if c["answered"] else ""}"><div class="chead">{label} '
            f'<strong>{escape(c["author"])}</strong> <span class="muted">· {local_dt(c.get("published"))} · '
            f'{escape(yt_titles.get(c["video_id"], c["video_id"] or ""))}'
            f'{" · " + str(c["likes"]) + " like(s)" if c["likes"] else ""}'
            f'{" · " + str(c["replies"]) + " reply(ies)" if c["replies"] else ""}</span></div>'
            f'<div class="ctext">{escape(c["text"])}</div>'
            f'<div class="cactions"><a href="{escape(c["url"])}">Open on YouTube</a>{cmd}</div></li>')

    errors = "".join(f'<div class="warn">{escape(e)}</div>' for e in state.get("errors", []))
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>video-studio · statistics</title>
<style>
:root {{ --bg:#fafaf9; --fg:#1c1917; --muted:#78716c; --line:#e7e5e4; --card:#fff; --yt:#c4302b; --tt:#0f766e; --ok:#15803d; --todo:#b45309; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#1c1917; --fg:#f5f5f4; --muted:#a8a29e; --line:#44403c; --card:#292524; --yt:#f87171; --tt:#5eead4; --ok:#4ade80; --todo:#fbbf24; }} }}
* {{ box-sizing:border-box }} body {{ margin:0; font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; background:var(--bg); color:var(--fg) }}
main {{ max-width:1100px; margin:0 auto; padding:28px 20px 60px }} h1 {{ font-size:22px; margin:0 0 4px }} h2 {{ font-size:17px; margin:34px 0 12px }}
a {{ color:inherit }} .muted {{ color:var(--muted); font-size:13px }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; margin-top:18px }}
.tile {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px }}
.label {{ color:var(--muted); font-size:13px }} .value {{ font-size:28px; font-weight:650; font-variant-numeric:tabular-nums }} .sub {{ color:var(--muted); font-size:13px }}
table {{ width:100%; border-collapse:collapse; background:var(--card); border:1px solid var(--line); border-radius:10px; overflow:hidden }}
th, td {{ padding:9px 10px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top }} th {{ font-size:12px; color:var(--muted); font-weight:600 }}
.num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap }} .delta {{ color:var(--ok); font-size:12px }} .delta.neg {{ color:var(--todo) }}
.plat {{ font-size:12px; font-weight:600 }} .plat.youtube {{ color:var(--yt) }} .plat.tiktok {{ color:var(--tt) }} .spark {{ color:var(--muted) }}
.badge {{ font-size:11px; border:1px solid var(--line); border-radius:99px; padding:1px 7px; color:var(--muted) }}
.badge.ok {{ color:var(--ok); border-color:currentColor }} .badge.todo {{ color:var(--todo); border-color:currentColor }}
ul.comments {{ list-style:none; padding:0; margin:0; display:grid; gap:10px }}
ul.comments li {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px 14px }} ul.comments li.done {{ opacity:.7 }}
.ctext {{ margin:6px 0; white-space:pre-wrap }} .cactions {{ display:flex; gap:14px; flex-wrap:wrap; align-items:center; font-size:13px }}
.cmd {{ font:12px ui-monospace,Consolas,monospace; background:var(--bg); border:1px solid var(--line); border-radius:6px; padding:2px 6px; user-select:all }}
.warn {{ background:var(--card); border:1px solid var(--todo); color:var(--todo); border-radius:8px; padding:8px 12px; margin-top:10px; font-size:14px }}
.note {{ color:var(--muted); font-size:13px; margin-top:8px }}
</style></head><body><main>
<h1>video-studio statistics</h1>
<div class="muted">Last collection: {local_dt(state.get("collected_at"))} · changes computed over 24 h</div>
{errors}
<div class="tiles">{''.join(tiles)}</div>
<h2>Videos</h2>
<table><thead><tr><th>Platform</th><th>Video</th><th>Published</th><th class="num">Views</th><th class="num">Likes</th><th class="num">Comments</th><th class="num">Shares</th><th>Trend</th></tr></thead>
<tbody>{''.join(rows) or '<tr><td colspan="8" class="muted">No video collected.</td></tr>'}</tbody></table>
<div class="note">TikTok counters may lag by several hours. Shares: not provided by YouTube.</div>
<h2>YouTube comments</h2>
<ul class="comments">{''.join(citems) or '<li class="muted">No comment.</li>'}</ul>
<div class="note">Reply from the PC with the command shown under each comment, or answer them one by one with
<code class="cmd">tools\\deploy\\reply_comment.ps1</code>. TikTok: comment contents are not available through the public API; their number is in the table.</div>
</main></body></html>
"""
