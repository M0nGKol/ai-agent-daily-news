# Deployment Plan

This plan prepares the Daily AI Learning Brief Agent for reliable scheduled
delivery without deploying automatically.

## 1. Target Deployment

Use GitHub Actions for the MVP:

- `news_digest.yml`: daily AI engineering news digest at 07:00 ICT.
- `daily_digest.yml`: manual-only topic dispatcher for one-off topic cards.
- `python -m app.jobs.run`: unified entrypoint controlled by `DIGEST_MODE`.

Recommended production mode today:

```text
DIGEST_MODE=digest
```

Recommended next product mode later:

```text
DIGEST_MODE=mixed
```

`mixed` does not exist yet. Add it after the learning/news/open-source planner is
implemented.

## 2. Pre-Deployment Checklist

Run locally before pushing:

```bash
python -m pytest -q
python -m app.jobs.daily_digest
```

For a Telegram smoke test, use the real `.env` locally and check that one digest
appears in your target channel or chat.

Do not commit:

- `.env`
- SQLite databases
- source state files
- API keys
- Telegram bot tokens
- Telegram chat IDs

## 3. Required Secrets

Add these in GitHub:

`Settings -> Secrets and variables -> Actions -> Secrets`

| Secret | Required | Notes |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Yes | Token from BotFather. Rotate it if it was ever shared. |
| `TELEGRAM_CHAT_ID` | Yes | Channel/group/user chat ID. Channel IDs usually start with `-100`. |
| `LLM_API_KEY` | Recommended | Gemini key when using Gemini through OpenAI-compatible endpoint. |
| `DATABASE_URL` | Strongly recommended | Use Neon/Supabase/Postgres for durable state. |
| `TELEGRAM_COMMAND_ALLOWED_IDS` | Optional | Chat/user IDs allowed to run `/digest`; use when commands come from private chat. |
| `SEMANTIC_SCHOLAR_API_KEY` | Optional | Higher Semantic Scholar rate limits. |

## 4. Required Variables

Add these in:

`Settings -> Secrets and variables -> Actions -> Variables`

| Variable | Recommended value |
| --- | --- |
| `LLM_PROVIDER` | `openai` |
| `LLM_MODEL` | `gemini-2.5-flash` |
| `LLM_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai` |
| `MAX_DIGEST_ITEMS` | `5` |
| `HTTP_TIMEOUT_SECONDS` | `20` |
| `RSS_FEEDS` | Leave blank to use curated defaults. |
| `DIGEST_REPEAT_LOOKBACK_DAYS` | `14` |
| `MAX_ITEMS_PER_SOURCE_DOMAIN` | `1` |
| `GDELT_ENABLED` | `true` |
| `GDELT_QUERY` | Leave blank to use curated AI query, or tune for your niche. |
| `GDELT_TIMESPAN` | `3d` |
| `GDELT_MAX_RECORDS` | `50` |
| `TELEGRAM_DIGEST_COMMAND` | `/digest` |
| `TELEGRAM_COMMAND_POLL_TIMEOUT_SECONDS` | `25` |

Topic-card variables, only needed if you re-enable scheduled topic delivery:

| Variable | Recommended value |
| --- | --- |
| `TOPIC_TIMEZONE` | `Asia/Phnom_Penh` |
| `TOPIC_SEND_START_HOUR` | `8` |
| `TOPIC_SEND_END_HOUR` | `22` |
| `TOPIC_DUE_WINDOW_MINUTES` | `75` |

## 5. Database Plan

For local development:

```text
DATABASE_URL=sqlite:///./daily_digest.db
```

For deployment:

```text
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST/DB?sslmode=require
```

Why Postgres is recommended:

- Prevents repeated topic sends if hourly dispatch is enabled.
- Prevents repeated news cards by preserving recently sent source URLs.
- Persists digest history across GitHub Actions runs.
- Keeps delivery status even when GitHub runners are recreated.

Current caveat:

- Dynamic source discovery still uses JSON files under `SOURCE_STATE_DIR`.
- GitHub Actions caches that directory for now.
- A future improvement should move source discovery state into Postgres.

## 6. Telegram Plan

Recommended target:

- Use a private Telegram channel if you only want broadcast-style delivery.
- Add the bot as administrator.
- Give it permission to post messages.
- Use the channel chat ID as `TELEGRAM_CHAT_ID`.

Smoke test:

```bash
python -m app.jobs.daily_digest
```

If nothing sends, check:

- Bot is admin in the channel.
- `TELEGRAM_CHAT_ID` is the channel ID, not your user ID.
- The workflow logs do not show `TELEGRAM_BOT_TOKEN is required`.

Manual `/digest` command:

- GitHub Actions cannot react instantly to Telegram commands because it is not a
  long-running process.
- Run `python -m app.jobs.telegram_command_bot` on your laptop, VM, or Cloud Run
  service if you want `/digest` to trigger delivery.
- If you send `/digest` from a private chat, set `TELEGRAM_COMMAND_ALLOWED_IDS`
  to your private Telegram user/chat ID.
- If `TELEGRAM_COMMAND_ALLOWED_IDS` is blank, the worker only accepts commands
  from `TELEGRAM_CHAT_ID`.

## 7. GitHub Actions Rollout

1. Push the current branch to GitHub.
2. Add all secrets and variables.
3. Open the Actions tab.
4. Run `Daily AI Engineering News Digest` manually.
5. Confirm the run is green.
6. Confirm Telegram receives the digest.
7. Leave the scheduled workflow enabled.

The current daily schedule is:

```text
0 0 * * *  # 00:00 UTC = 07:00 ICT
```

## 8. Monitoring

For the MVP, monitor through:

- GitHub Actions run status.
- Telegram delivery success.
- Digest rows in the database.
- Workflow logs for collector failures.

Useful failure checks:

- RSS collector failures: usually feed/network issues.
- GDELT collector failures: usually temporary API/network issues or an overly broad query.
- Semantic Scholar failure: missing key or rate limit.
- LLM failure: bad `LLM_BASE_URL`, invalid key, or provider outage.
- Telegram failure: bot permission or wrong chat ID.

## 9. Rollback Plan

If a deployment fails:

1. Disable the workflow schedule temporarily.
2. Fix secrets/variables first.
3. Re-run the workflow manually.
4. If code caused the issue, revert the latest commit.
5. Re-run tests locally before pushing again.

Do not rotate database credentials unless logs show they were exposed.
Do rotate Telegram and LLM tokens if they appear in chat, screenshots, logs, or commits.

## 10. Next Deployment Upgrade

After MVP is stable, upgrade toward the intended agent:

1. Add `DIGEST_MODE=mixed`.
2. Add a GitHub open-source collector.
3. Add a daily planner table for 5 mixed cards.
4. Re-enable hourly topic dispatch only after Postgres is configured.
5. Move source discovery state from JSON cache into the database.
6. Add Telegram feedback buttons for personalization.
