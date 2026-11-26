# Editing workstation setup

To do once on the PC used to edit the videos (Windows here; on Linux, same steps with `python3`).
**Publishing** does not happen from this machine but from the Linux server: see
[server.md](server.md). No secret is stored on this machine.

## 1. Prerequisites

| Item | Check |
|---|---|
| Python 3.10 or later | `py --version` |
| FFmpeg in PATH (editing, cover frames); on Windows: `scoop install ffmpeg` | `ffmpeg -version` |
| OpenSSH client and `tar`, built into Windows 10/11 | `ssh -V`, `tar --version` |
| Password-less SSH key to the server | `ssh -o BatchMode=yes <VS_SERVER> hostname` |
| Chrome with a profile dedicated to the project's Google account (OAuth authorizations) | `chrome://version` → "Profile Path" |

## 2. Python environment

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -r requirements-dev.txt
```

If PowerShell refuses the activation script:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

In every new PowerShell window, only the `.venv` activation is needed.

## 3. Machine configuration (.env)

```powershell
Copy-Item .env.example .env
```

Fill in `VS_SERVER`, `VS_SERVER_DIR`, the vault settings (copied to the server on deployment) and
`VS_CHROME_PATH` / `VS_CHROME_PROFILE`. Details of every setting: [configuration.md](configuration.md).

## 4. Check

```powershell
python -m pytest                                                       # unit tests, no network
python videos\<folder>\montage\<script>.py                          # a full edit of one of your videos
```

## 5. Publishing server

See [server.md](server.md): deployment, secrets in gopass, timers.
Creating the platform apps: [platforms.md](platforms.md).
