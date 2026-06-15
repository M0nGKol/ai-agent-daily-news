# Security Review

Review date: 2026-06-11

Scope: MVP batch agent under `/Users/apple/ai-agents-daily-news`, including
configuration, collectors, summarization, persistence, Telegram delivery,
GitHub Actions, dependency declarations, and repository rules. No live provider
calls or external vulnerability database lookups were performed.

## Summary

The MVP is on a reasonable security track: runtime secrets are read from
environment variables, `.env` files are ignored, `.env.example` contains only
placeholders, GitHub Actions uses repository secrets, Telegram messages escape
HTML, source URLs are required for publishable digest items, and outbound
collection currently uses APIs or RSS rather than HTML scraping.

The main remaining risks are operational hardening items: dependency pinning
and vulnerability scanning, explicit rate-limit/backoff behavior, stronger
guardrails around configured RSS and LLM endpoints, broader log-redaction test
coverage, and clear rules for tests that touch external APIs.

## Confirmed Controls

- Secrets are configured through environment variables and `.env`; no hardcoded
  tokens were found by a regex scan for common secret patterns.
- `.gitignore` excludes `.env`, `.env.*`, local SQLite databases, virtual
  environments, coverage output, caches, and editor files.
- `.env.example` documents required variables without real values.
- `Settings` uses `repr=False` for sensitive fields such as Telegram, LLM, and
  Semantic Scholar keys.
- The daily job configures a redacting logging filter before execution.
- Telegram delivery catches HTTP exceptions without logging the bot-token URL,
  escapes message content for HTML parse mode, and disables link previews.
- GitHub Actions has `permissions: contents: read`, no pull-request trigger,
  and reads tokens from `secrets.*` instead of committing them.
- Collectors use arXiv API, Semantic Scholar API, and RSS feeds. No generic
  website scraping was found.
- Fact-checking requires source URLs and blocks obvious unsupported numeric
  claims and extra URLs in summaries.

## Findings And Recommendations

### P1: Add Stronger Outbound Request Guardrails

`arXiv`, `Semantic Scholar`, and `Telegram` endpoints are fixed and trusted, but
RSS feed URLs are configured at runtime and the LLM provider/base URL can also
be environment-driven. This is acceptable for a local MVP, but before running in
shared CI or production:

- Validate configured RSS feed URLs: allow only `http` and `https`, reject local
  and private-network hosts, and cap the number of feeds.
- Fetch RSS with an explicit HTTP client timeout and response-size limit, then
  parse the fetched bytes with `feedparser`.
- Keep an allowlist of approved RSS domains for the scheduled digest.
- Treat configurable LLM base URLs/provider URLs as trusted deployment config
  only; prefer an allowlist of known providers for CI.

### P1: Implement Rate Limits, Retries, And Backoff

Current collectors use timeouts for API clients but do not implement provider
rate limits, `Retry-After`, or exponential backoff. Add:

- Per-provider request caps and cooldowns.
- Retry logic only for transient errors such as 429, 502, 503, and 504.
- Respect for `Retry-After` when present.
- A hard daily maximum for RSS feeds and collected items.
- Tests that prove failures degrade to partial results instead of failing the
  whole digest.

### P1: Harden Dependency And CI Supply Chain

`requirements.txt` uses lower-bound constraints (`>=`) without a lockfile or
hashes. This is convenient for early development but non-reproducible in CI.

Recommended MVP hardening:

- Generate a pinned lockfile with hashes, for example using `pip-tools`.
- Add `pip-audit` or an equivalent vulnerability scan to CI.
- Enable Dependabot for Python dependencies and GitHub Actions.
- Remove unused dependencies when confirmed unused, such as `requests`.
- Consider pinning GitHub Actions to full commit SHAs for higher-assurance
  scheduled jobs.

### P1: Broaden Secret Redaction Coverage

Logging redaction is present and useful. Strengthen it with tests and complete
coverage:

- Include `LLM_API_KEY` and optionally `TELEGRAM_CHAT_ID` in explicit
  `extra_secret_values` passed to logging setup.
- Add unit tests for redacting assignment-style secrets, authorization headers,
  query-string tokens, Telegram bot-token URLs, and raw configured secret
  values.
- Avoid using feed URLs with embedded API tokens. If unavoidable, strip or mask
  token query parameters before logging or persisting source names.

### P2: Treat Source Text As Prompt-Injection Input

Article titles, abstracts, and RSS summaries can contain hostile instructions.
The prompt already says to use only source fields, and output validation catches
some unsafe claims, but the source text should still be treated as untrusted.

Recommended additions:

- Delimit source fields clearly as untrusted data in prompts.
- Cap title, abstract, and RSS summary length before sending to an LLM.
- Validate the LLM response against a strict schema.
- Keep deterministic fallback summaries for provider failures.
- Expand grounding checks beyond numbers and URLs where practical.

### P2: Define Data Retention For Raw Payloads

The database stores `raw_payload` for collected source items. This is useful for
debugging, but can retain third-party content and metadata longer than needed.

Recommended additions:

- Document what raw payloads may contain.
- Avoid storing configured feed URLs with secret query parameters.
- Add a retention policy for local SQLite and future PostgreSQL deployments.
- Consider storing only normalized fields once debugging needs are satisfied.

### P2: Clarify Telegram Operations

Telegram bot tokens are sensitive because the token appears in Bot API URLs.
Current delivery code avoids logging those URLs directly. Operationally:

- Store `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` only in `.env` locally and
  GitHub Secrets in CI.
- Rotate the bot token immediately if it appears in logs, issues, commits, or
  screenshots.
- Use a dedicated bot and destination chat/channel for the digest.
- Keep `disable_web_page_preview=True` unless previews are explicitly needed.

### P2: Add Test Guardrails For External APIs

No test files were present during this review. Before expanding the agent:

- Add unit tests with injected/fake HTTP clients for collectors, Telegram, and
  LLM summarization.
- Mark any real-provider tests as integration tests and exclude them from the
  default `pytest` command.
- Add CI checks that fail if an unmarked test attempts a real external call.
- Add tests for graceful API failures and partial collector success.

## MVP Security Checklist

### Secrets And Configuration

- [x] `.env` and `.env.*` are ignored, with `.env.example` committed.
- [x] GitHub Actions reads sensitive values from `secrets.*`.
- [x] Sensitive settings avoid repr exposure.
- [ ] Add automated log-redaction tests.
- [ ] Include all runtime secret values in explicit logging redaction.
- [ ] Document secret rotation steps for Telegram and provider keys.

### Collection And Scraping Safety

- [x] Use APIs or RSS before scraping.
- [x] No HTML scraping found in the current code.
- [ ] Validate configured RSS feed URLs and reject private-network targets.
- [ ] Add RSS fetch timeout, response-size limit, and feed count cap.
- [ ] Document robots.txt checks as mandatory before any future scraping.

### Rate Limits And Failure Handling

- [x] Fixed API collectors have timeout parameters.
- [x] Collector failures return empty results or partial results gracefully.
- [ ] Add provider-specific retry/backoff with `Retry-After` support.
- [ ] Add request caps for scheduled runs.
- [ ] Add tests for network failures, invalid responses, and rate limits.

### Summarization And Fact Checking

- [x] Digest items require source URLs.
- [x] Summaries are validated before publishing.
- [x] Telegram HTML content is escaped.
- [ ] Treat source text as untrusted prompt input with delimiters and size caps.
- [ ] Expand schema validation and grounding tests.

### Dependencies And CI

- [x] CI uses minimal `contents: read` permission.
- [x] CI does not run on pull requests by default.
- [ ] Pin Python dependencies with hashes for reproducible CI.
- [ ] Add dependency vulnerability scanning.
- [ ] Add Dependabot for Python and Actions.
- [ ] Consider pinning Actions to commit SHAs for hardened scheduled delivery.

### Storage And Retention

- [x] Local database files are ignored.
- [ ] Document retention for SQLite and future PostgreSQL data.
- [ ] Decide whether raw collector payloads are needed long term.
- [ ] Redact or avoid storing tokenized feed URLs in source metadata.

## Assumptions

- The project is currently an MVP batch job, not a public web service.
- Repository secrets are configured in GitHub and are not visible locally.
- The review did not include live API calls, Telegram sends, or an online
  dependency vulnerability scan.
- The workspace appears nested under a larger parent Git worktree; this review
  only covers files under `/Users/apple/ai-agents-daily-news`.
- Existing `.pyc` and cache files are local artifacts; if any are tracked in a
  future repository, remove them from version control.
