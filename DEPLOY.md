# Hosting the bot on GitHub Actions

Once this is done, GitHub runs your digest automatically every day at **07:00 ICT**
on its own servers — your computer does not need to be on.

> Before you start: rotate your Gemini API key (it was shared in chat) and make sure
> `.env` is never committed. It is already in `.gitignore`, so it will be skipped.

## 1. Create a GitHub repository

On github.com, click **New repository**. Make it **Private** (it contains your bot
logic; secrets are added separately, not in code). Do not add a README/.gitignore —
you already have files. Copy the repo URL it shows you.

## 2. Push your code

From the project folder in a terminal:

```bash
cd /path/to/ai-agents-daily-news

# only if it is not already a git repo:
git init
git branch -M main

git add .
git commit -m "AI engineering news digest bot"
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

Confirm on GitHub that the files uploaded and that **`.env` is NOT there** (it must
stay local).

## 3. Add your secrets and variables

In the repo: **Settings → Secrets and variables → Actions**.

Under the **Secrets** tab → **New repository secret**, add:

| Secret name            | Value                                  |
|------------------------|----------------------------------------|
| `TELEGRAM_BOT_TOKEN`   | your bot token                         |
| `TELEGRAM_CHAT_ID`     | your channel id (e.g. `-1003...`)      |
| `LLM_API_KEY`          | your **new** Gemini key                |
| `DATABASE_URL`         | your Neon Postgres URL                 |

Under the **Variables** tab → **New repository variable**, add:

| Variable name   | Value                                                        |
|-----------------|--------------------------------------------------------------|
| `LLM_PROVIDER`  | `openai`                                                     |
| `LLM_MODEL`     | `gemini-2.5-flash`                                           |
| `LLM_BASE_URL`  | `https://generativelanguage.googleapis.com/v1beta/openai`    |

(Optional variables: `MAX_DIGEST_ITEMS`, `RSS_FEEDS`, `HTTP_TIMEOUT_SECONDS` — leave
unset to use defaults.)

Secrets are hidden and encrypted; variables are plain config. The workflow reads
`secrets.*` and `vars.*` for exactly these names.

## 4. Enable Actions

Go to the **Actions** tab. If prompted, click **I understand my workflows, enable
them**. You should see two workflows:

- **Daily AI Engineering News Digest** ← the live one (daily at 07:00 ICT)
- **Daily AI Topics (legacy, manual only)** ← old topic cards, no schedule

## 5. Test it now (don't wait for the schedule)

Open **Actions → Daily AI Engineering News Digest → Run workflow → Run workflow**.
Watch the run; when it goes green, check your Telegram channel for the digest.

If it fails, click the run → the **Run news digest** step shows the error (usually a
missing/typo'd secret or variable name).

## 6. You're hosted

From now on it runs by itself at 07:00 ICT daily. The **Run workflow** button is
always there for an on-demand digest.

### Good to know

- GitHub **disables scheduled workflows after 60 days of no repo activity**. Any
  commit, or one manual run, resets the clock.
- Scheduled runs can start a few minutes late under load — fine for a daily digest.
- Source-discovery state persists between runs via the Actions cache (already wired
  in the workflow), so the source pool keeps learning.
