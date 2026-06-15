# Security Policy

## Supported Scope

This repository is an MVP batch agent for collecting AI technology sources,
summarizing them, and sending a daily Telegram digest. Security review and
support apply to the active mainline code and scheduled-job configuration.

## Reporting A Vulnerability

Do not post secrets, tokens, chat IDs, database URLs, or exploit details in
public issues. Use the repository's private vulnerability reporting channel if
enabled, or contact the maintainers out of band with:

- Affected files or workflow.
- Steps to reproduce.
- Potential impact.
- Whether any secret may have been exposed.

## Secret Handling

- Never commit real `.env` files, Telegram bot tokens, provider API keys, or
  database credentials.
- Use `.env` for local development and GitHub Secrets for CI.
- Keep `.env.example` limited to placeholder values.
- Rotate any token that appears in logs, commits, issues, screenshots, or test
  fixtures.

## External Services

- Prefer APIs or RSS feeds before scraping.
- Do not scrape sites that disallow crawling.
- Keep external API tests mocked by default; mark real-provider tests as
  integration tests.
- Handle provider failures gracefully and avoid logging request headers,
  authorization values, or tokenized URLs.

## Dependency Hygiene

For production-like scheduled runs, use pinned dependencies, dependency
vulnerability scanning, and regular updates for Python packages and GitHub
Actions.
