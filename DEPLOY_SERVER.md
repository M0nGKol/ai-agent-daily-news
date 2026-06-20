# Hosting on a Personal Ubuntu/Debian Server

The digest runs as a **systemd timer** — no GitHub Actions required. Your server
runs the job at **07:00 ICT (00:00 UTC)** daily.

---

## Prerequisites

- Ubuntu 22.04+ / Debian 12+ server with SSH access
- Python 3.11+ available (`python3 --version`)
- Your `.env` file with all secrets (see `.env.example`)

---

## 1. Copy the project to your server

From your Mac, `rsync` the project over (or `git clone` if you have the repo
on a remote):

```bash
rsync -av --exclude='.venv' --exclude='__pycache__' \
  /path/to/ai-agents-daily-news/ \
  youruser@yourserver:/tmp/ai-agents-daily-news/
```

Or via git:

```bash
# on the server
git clone https://github.com/<you>/<repo>.git /tmp/ai-agents-daily-news
```

---

## 2. Run the install script

SSH into the server and run:

```bash
cd /tmp/ai-agents-daily-news
sudo bash deploy/install.sh youruser
```

Replace `youruser` with the Linux username that should own and run the job
(e.g. `ubuntu`, `mongkol`). The script:

- Installs Python + system packages via `apt`
- Syncs the app to `/opt/ai-agents-daily-news`
- Creates a `.venv` and installs pip dependencies
- Installs and enables the systemd timer

> **`.env` note:** If `.env` exists in the source directory it is copied
> automatically. Otherwise the script warns you — copy it manually:
>
> ```bash
> sudo cp /tmp/ai-agents-daily-news/.env /opt/ai-agents-daily-news/.env
> sudo chmod 600 /opt/ai-agents-daily-news/.env
> sudo chown youruser:youruser /opt/ai-agents-daily-news/.env
> ```

---

## 3. Test it immediately

Trigger the digest without waiting for the timer:

```bash
sudo systemctl start ai-digest@youruser.service
```

Watch the output live:

```bash
journalctl -u ai-digest@youruser.service -f
```

Check your Telegram channel — the digest should arrive within a minute.

---

## 4. Verify the schedule

```bash
systemctl list-timers ai-digest*
```

You'll see the next trigger time. It should say `Sat 2026-06-21 00:00:00 UTC`
(or the next upcoming midnight UTC).

---

## Useful day-to-day commands

| Task | Command |
|---|---|
| Run digest now | `sudo systemctl start ai-digest@youruser.service` |
| Check timer | `systemctl status ai-digest@youruser.timer` |
| View recent logs | `journalctl -u ai-digest@youruser.service -n 50` |
| Tail logs live | `journalctl -u ai-digest@youruser.service -f` |
| Disable schedule | `sudo systemctl disable ai-digest@youruser.timer` |
| Re-enable schedule | `sudo systemctl enable --now ai-digest@youruser.timer` |

---

## Updating the app

When you push changes, re-run the install script — it `rsync`s the new code
and restarts nothing (the timer fires on schedule as usual). Your `.env` and
`state/` directory are preserved.

```bash
sudo bash /opt/ai-agents-daily-news/deploy/install.sh youruser
```

---

## State persistence

Unlike GitHub Actions (which needs the cache workaround), on your server the
`state/` directory at `/opt/ai-agents-daily-news/state` simply persists on
disk between runs. No extra configuration needed.

---

## Secrets checklist

Make sure `/opt/ai-agents-daily-news/.env` contains:

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
LLM_API_KEY=...
LLM_PROVIDER=openai
LLM_MODEL=gemini-2.5-flash
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
DATABASE_URL=sqlite:///./daily_digest.db   # or your Neon Postgres URL
```
