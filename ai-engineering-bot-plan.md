# AI Engineering News Bot — Refined Plan

A daily Telegram digest that keeps you sharp on the **craft of AI engineering** — building, deploying, and operating AI systems. Not general AI news.

## 1. Scope guardrail (the most important part)

The goal is **learning the craft of AI engineering** — staying technically current. So the one filter question is:

> *"Does this teach me something technical about how AI systems are built?"*

This is a **substance vs hype** test, not an actionability test. Unreleased big-tech work stays in if it has real technical content (you learn the approach); pure announcements are dropped.

**In-scope buckets (every item must map to one — if it can't, it's hype, drop it):**
1. LLM serving & inference (vLLM, TGI, quantization, latency/cost)
2. Agents & orchestration (frameworks, tool use, multi-agent)
3. RAG & retrieval (vector DBs, chunking, rerankers)
4. Fine-tuning & training (LoRA, datasets, post-training)
5. Eval & observability (benchmarks, tracing, guardrails)
6. Notable OSS tooling & infra

**Keep** — anything with technical substance, released or not: new model architectures, training methods, serving/infra approaches, benchmark results, eng deep-dives, technical reports.

**Drop** — items with no technical substance: funding rounds, valuations, exec hires/drama, partnership PR, regulation/policy, AGI think-pieces, "excited to announce" with no details.

**Big tech is a source, not a bucket.** Google/Meta/OpenAI/DeepSeek items flow through the same 6 buckets and the same substance filter — a new Gemini technical report → "serving/inference" or "training"; a "$X invested in AI" headline → dropped. No special-case logic; one rule governs everything.

## 2. Sources (curated > open web search)

Curated feeds give far higher signal than raw web search. Use:

- **GitHub Trending** — filtered by topic/language (Python), daily window. API or scrape `github.com/trending`.
- **Hugging Face** — trending models/datasets, papers page.
- **arXiv** — `cs.LG`, `cs.CL` recent, filtered by keyword.
- **High-signal blogs/changelogs** — a small allowlist (e.g. vLLM, LangChain, LlamaIndex, Anthropic/OpenAI eng blogs, a few practitioners).
- **Big-tech AI/research blogs** — Google DeepMind, Meta AI, OpenAI, Microsoft Research, NVIDIA, DeepSeek release & research pages. These feed the same 6 buckets; the substance filter strips out the PR.

Keep web search as a *fallback*, not the primary engine — it's where scope creep enters.

## 2b. Dynamic source discovery (so it feels alive)

**Sources** = *where* you look. **Items** = *what* you find. Most sources above are already dynamic by nature (Trending, arXiv recent, HN, r/LocalLLaMA change daily), so "same sources" ≠ "same news." The discovery layer keeps the *source pool itself* growing instead of a hand-maintained allowlist.

**Self-expanding allowlist with a trust gate.** Seed with the current trusted list, then on every run:

1. **Harvest candidates** from the dynamic feeds — outbound links in high-signal HN posts, blog domains cited in trending repo READMEs, authors of trending papers. New voices surface organically.
2. **Pool, don't trust yet.** New domains go into a `candidates` list with a counter, not straight into the feed.
3. **Promote on evidence.** When a candidate appears N times in high-signal contexts (or produces a high-scoring item), promote it to `trusted`.
4. **Demote on decay.** Track each source's hit rate (posted vs dropped). Quiet or hype-prone sources get demoted to candidate or dropped. The list self-prunes.

The pool **breathes**: new labs/blogs/authors enter as the field moves, dead ones fall out, no hand-editing.

**Two freshness controls on top:**

- **Novelty boost** in scoring — small bonus to items from a source/author not posted in 14+ days, so the digest rotates instead of featuring the same 3 places.
- **Bucket rotation** — cap items per bucket per run so the topic mix varies day to day.

**State files:**

```
state/
  trusted_sources.json    # promoted, active sources
  candidate_sources.json  # {domain: {count, first_seen, last_high_signal}}
  source_stats.json       # {domain: {posted, dropped, last_posted}}  -> drives promote/demote + novelty
```

Discovery widens the funnel; the substance filter (Section 1) keeps the output tight. They work as a pair.

## 3. Per-item output format

```
🔧 [Title]
• 2–3 bullet summary of what it is / what changed
💡 Why it matters for AI engineers: <one sharp line>
🔗 Source: <link>
```

The "why it matters" line is your differentiator — it turns a feed into your voice. Have the LLM generate it, scoped to the engineering angle.

## 4. Ranking & volume

- Score each candidate 0–10 on relevance to the 6 buckets + recency + signal (stars/velocity, author credibility).
- Post **only the top 3–5 per run.** A short high-signal channel beats a noisy one.
- De-dupe against a small history file (last ~14 days of posted URLs) so nothing repeats.

## 5. Images — drop them

Most repos/papers have no meaningful image; generating decorative AI art adds cost and noise. **Skip per-item images.** Optional: one static header banner per daily digest. Spend the effort on the "why it matters" lines instead.

## 6. Architecture (Python)

```
fetch/        # one module per source -> normalized Item objects
  github.py
  huggingface.py
  arxiv.py
  blogs.py
filter.py     # bucket classification + drop out-of-scope
score.py      # relevance scoring
summarize.py  # LLM call: bullets + "why it matters" line
dedupe.py     # history check (json/sqlite of posted URLs)
publish.py    # Telegram Bot API sendMessage (Markdown/HTML)
main.py       # orchestrate; run once per schedule
state/
  history.json
```

**Item schema:** `title, url, source, bucket, raw_text, summary, why_it_matters, score, date`.

## 7. Scheduling

Run once daily (e.g. 07:00). Cron, GitHub Actions (free, no server), or your existing host. GitHub Actions is the simplest zero-cost option for a script like this.

## 8. Build order (suggested)

1. One fetcher (GitHub Trending) → print normalized items.
2. Add filter + score → confirm only relevant items survive.
3. Add LLM summarize → check the "why it matters" quality.
4. Add dedupe + Telegram publish → end-to-end with one source.
5. Add remaining fetchers (HF, arXiv, blogs).
6. Schedule it.

Ship with one source working end-to-end before adding the rest. That keeps the engineering tight — same discipline you're applying to the content.

## 9. Guardrails against scope creep

- Hard-code the 6 buckets; anything unclassifiable is dropped, not "miscellaneous."
- Cap posts per run (3–5).
- Quarterly: review what you posted; cut any bucket that's consistently low-signal.
