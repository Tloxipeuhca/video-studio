# Platform setup

Each platform needs a developer app, then a one-time authorization. The scripts then manage the
tokens on their own. Suggested order: YouTube, then TikTok (Instagram: implemented but untested,
see its section). Every step is done in the **Chrome profile of the project account**
(`VS_CHROME_PROFILE`).

Credentials go into **gopass on the server**, never into a file that stays on the PC. Two ways to
put them there:

- **Copy from the PC**: drop the JSON file temporarily into `secrets\`, run
  `py tools\secrets\push_secrets.py --apply` (copy + read-back), then delete `secrets\`.
- **Type it on the server**: `gopass cat <prefix>/tiktok/app`, paste the JSON and finish with
  Ctrl+D (through the `VS_GOPASS_CMD` wrapper if there is one).

Authorizations (`--auth-only`) are started from the PC with `tools\deploy\auth_tunnel.ps1`: an SSH
tunnel brings the authorization page to the PC Chrome, and the token is written straight into
gopass on the server. gopass entries: see [configuration.md](configuration.md).

| Platform | What you create | gopass entries (`<prefix>/…`) | Authorization | Token lifetime |
|---|---|---|---|---|
| YouTube | Google Cloud project + "Desktop app" OAuth client | `youtube/client_secret` (downloaded JSON), then `youtube/token` | `tools\deploy\auth_tunnel.ps1 youtube` | Unlimited once the app is "In production" |
| TikTok | TikTok for Developers app (Login Kit + Content Posting API) | `tiktok/app`, then `tiktok/token` | `tools\deploy\auth_tunnel.ps1 tiktok` | 24 h, renewed automatically for 365 days |
| Instagram (untested) | Meta app + business portfolio, Instagram API (Unified login) | `instagram.token.json` | `python tools/publish/instagram.py --set-token TOKEN` | Never expires (system-user token) |

## YouTube

On console.cloud.google.com, with the project's Google account.

1. **Project**: project picker → **New project** → `video-studio`, no organization → select it.
2. **API**: ☰ → APIs & Services → Library → *YouTube Data API v3* → **Enable**.
3. **Consent screen** (☰ → Google Auth Platform → Get started):
   - App name of your choice, support e-mail = the project's Google account.
   - Audience **External**, contact = the project's Google account.
   - Data access → add `youtube.upload`, `youtube.readonly`, `youtube.force-ssl`.
   - Audience → **Publish app** → status **In production** (otherwise the token expires every 7 days).
4. **Client**: Clients → Create client → **Desktop app**, name `video-studio-desktop`
   → Download the JSON → store it as `youtube/client_secret` (see above: `push_secrets.py` accepts
   the original name `client_secret_*.json`).
5. **Authorize**: `tools\deploy\auth_tunnel.ps1 youtube`, open the printed address, pick the account,
   then Advanced → Go to *your app* (unsafe). This warning is normal for a personal app.

Limits: 100 uploads per day. Public from the first upload, no audit. A custom thumbnail requires a
verified phone (YouTube Studio → Settings → Channel → Feature eligibility).

## TikTok

As long as the app is not audited, direct posts are private (SELF_ONLY) and the account must be
private when posting.

1. **Developer account**: developers.tiktok.com → Log in → accept the terms.
2. **App**: Manage apps → Connect an app → **Individual** → app name of your choice (icon, category, description).
3. **Sandbox**: create a Sandbox environment, add your TikTok account as **Target user**.
4. **Products**:
   - **Login Kit** → platform **Desktop** → redirect URI `http://127.0.0.1:*/callback/` (exactly, with `*` as the port: the script picks a free port between 47821 and 47825).
   - **Content Posting API** → enable **Direct Post**.
   - **Display API** (statistics): see [statistics.md](statistics.md).
5. **Scopes**: `user.info.basic`, `video.publish`, `video.upload` (added by Login Kit and Content Posting API).
   They must match `VS_TIKTOK_SCOPES` in `.env`.
6. **Credentials**: entry `tiktok/app` = `{"client_key": "...", "client_secret": "..."}`.
7. **Authorize**: `tools\deploy\auth_tunnel.ps1 tiktok`, then `selftest.py --online` on the server to check.

| Mode (`"tiktok": {"mode": …}`) | TikTok account | Result |
|---|---|---|
| `direct` | Must be private | Video published, visible to you only |
| `inbox` | Can be public | Draft in the TikTok app, confirmed with one tap |

Later, the audit lifts the restriction: website with privacy policy and terms of service, demo
video, from a few days to two weeks. Then: `"privacy": "PUBLIC_TO_EVERYONE"`.

## Instagram (implemented, untested)

The Instagram module works with the steps below, but it is no longer tested: the account used to
test it was suspended by Meta. It is not part of the default platforms (`--platforms youtube,tiktok`);
add `instagram` to `--platforms` to use it.

Recent Meta apps use **API setup with Unified login** (the former "Instagram login" is no longer
offered). The token is a system-user token **that never expires**. Prerequisite: a **professional**
Instagram account (Creator or Business).

1. **Developer account**: developers.facebook.com, with a Facebook account under your real name
   (not shown publicly, not visibly linked to the Instagram account).
2. **App**: My Apps → Create app → app name of your choice → use case *Content management* →
   **Manage messaging & content on Instagram** → no business portfolio for now → Create app.
3. **Business portfolio** (required for Unified login): Use cases → Customize → **API setup with
   Unified login** → **+ Business portfolio** → create one with the project e-mail, confirm the
   e-mail, attach the app. Skip the business verification.
4. **Configuration**: step 1 → **Create new configuration** → keep the template (System-user access
   token, expiration Never, `instagram_content_publish`, `instagram_manage_comments`) → **Create from
   template**. Redirect URL and Login URL stay empty.
5. **Tester**: **Roles** link → add the Instagram account as **Instagram Tester**, then accept it on
   instagram.com (Settings → Apps and websites → Tester invites).
6. **Token**: step 2 **Generate access tokens** → add the account → **Generate token** → copy it.
7. **Save it**: `python tools/publish/instagram.py --set-token THE_TOKEN`, then `--whoami` to check.

API version error: set `IG_GRAPH_VERSION` (default `v23.0`).

## Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| YouTube asks for authorization every week | Consent screen in "Testing" mode | Publish the app, then `auth_tunnel.ps1 youtube` |
| YouTube: "Thumbnail not applied" | Phone not verified, or video format without custom thumbnails | Verify the phone; the video is published anyway |
| YouTube: `access_denied`, or another app's page after authorizing | The redirect port is taken by another application | The script picks a free port among 47811 to 47815 on 127.0.0.1; close the conflicting app if none is free |
| TikTok: `unaudited_client_can_only_post_to_private_accounts` | Public account in `direct` mode | Make the account private, or use `inbox` mode |
| TikTok: "scope" error | The script requests a scope the app does not have | Align `VS_TIKTOK_SCOPES` with the app scopes |
| TikTok: `non_sandbox_target` error | Account not in the Sandbox Target users | Sandbox settings → Target users → Add account |
| TikTok: `redirect_uri` rejected | Different address in Login Kit | Enter exactly `http://127.0.0.1:*/callback/` |
| TikTok: no free port | Ports 47821 to 47825 all taken | Close the conflicting application, or change `REDIRECT_PORTS` in `tiktok.py` |
| Instagram: permission error | Missing permission or non-professional account | Check the app and the account type, generate a new token |
| Server: authorization page unreachable | Tunnel not open, or port taken on the PC | Use `auth_tunnel.ps1` (not `--auth-only` directly); the port printed by the server must be in the tunnel range |
| Server: `Secret not found` | Entry missing from gopass, or wrong prefix | `selftest.py` on the server; check `VS_GOPASS_PREFIX` in `.env` |
