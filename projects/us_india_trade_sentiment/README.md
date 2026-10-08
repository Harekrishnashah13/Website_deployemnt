# US–India Trade Deal: Social Sentiment

Collects Reddit and X (Twitter) discussion about the US–India trade deal / tariffs. The output
feeds two analyses that get compared: TF-IDF + a classical sentiment model, and an LLM.

**Stage 1 (this folder): data collection.** The TF-IDF and LLM stages come next.

## Setup

```bash
cd projects/us_india_trade_sentiment
pip install -r requirements.txt
cp .env.example .env   # then fill in the keys you have
```

### Credentials

| Source | Needed? | How to get it |
| --- | --- | --- |
| Reddit | Optional, but strongly recommended | https://www.reddit.com/prefs/apps → "create another app" → type **script**. Put the id (under the app name) and secret in `.env`. With keys you get ~100 req/min. Without keys the scraper uses anonymous endpoints (~10 req/min), and Reddit often blocks those. |
| X API | Optional | https://developer.x.com. The **Free tier cannot search**; recent search needs Basic or higher and only covers the **last 7 days**. |
| X login cookies (twscrape) | Free alternative to the API | See "X without the paid API" below. |
| X export | Alternative to the API | Any CSV/JSON of tweets (an Apify "Tweet Scraper" run, a manual export, etc.). Pass it with `--x-export file.csv`. Common column names (`full_text`, `likeCount`, `createdAt`, …) are mapped automatically. |

## Run

```bash
python scrape.py                                # Reddit posts + comments (+ X if token set)
python scrape.py --no-x --max-threads 50        # quick Reddit-only run
python scrape.py --no-reddit --x-export tweets.csv
python -m pytest -q                             # parser tests, no network needed
```

A full Reddit run (15 sources × 8 queries, plus comments from the 200 busiest threads) takes about
10 min with OAuth and over an hour without it. Use `--max-threads` and `--max-pages` to make it
faster.

Output goes to `data/raw/` (git-ignored): `reddit_*.csv`, `x_*.csv` and a combined `corpus_*.csv`.

### Google Colab

```python
!git clone https://github.com/Harekrishnashah13/Website_deployemnt.git
%cd Website_deployemnt/projects/us_india_trade_sentiment
!pip install -q -r requirements.txt
import os
os.environ["REDDIT_CLIENT_ID"] = "..."
os.environ["REDDIT_CLIENT_SECRET"] = "..."
!python scrape.py --no-x
```

## X without the paid API (twscrape)

`--x-source twscrape` searches X's **Latest** tab the same way the website does, logged in as your
account. The tweets are real and current. Scraping this way is against X's terms of service, and X
can lock or suspend accounts that do it, so **use a spare X account, not your main one**.

1. Log in to that account at https://x.com in Chrome.
2. Press F12 → **Application** tab → **Cookies** → `https://x.com`.
3. Copy the values of `auth_token` and `ct0`.
4. Set them (in `.env`, or `os.environ[...]` in Colab):
   ```
   X_USERNAME=your_spare_handle
   X_COOKIES=auth_token=PASTE_HERE; ct0=PASTE_HERE
   ```
5. Run:
   ```bash
   python scrape.py --no-reddit --x-source twscrape --max-tweets 2000 --x-since 2026-09-01
   python scrape.py --no-reddit --x-source twscrape --x-every 30   # live: every 30 min until Ctrl+C
   ```

Live mode appends only new tweets to `data/raw/x_live.csv`, so you can leave it running for days
and build a time series. The cookies are as sensitive as a password: anyone with them is logged in
as you. Never commit or share them. Logging out of X in that browser invalidates them.

If X rate-limits the account, twscrape waits for the limit to reset (about 15 minutes) and then
continues.

## Output schema

| column | meaning |
| --- | --- |
| platform | `reddit` / `x` |
| kind | `post`, `comment`, `tweet` |
| id, parent_id | item id; for comments this is the post id, for tweets the conversation id |
| created_utc | ISO-8601 UTC |
| author_hash | salted SHA-256 of the username (the dataset stores no raw handles) |
| community | subreddit (empty for X) |
| title, text | cleaned text (HTML entities decoded, URLs removed, whitespace collapsed) |
| score, num_replies | upvotes/likes, comment/reply count |
| url, query | link to the item, and the search query that found it |

## What gets collected

Queries, subreddits and the X query live in `config.py`. Posts and tweets are kept only when they
mention India **and** the US **and** trade/tariffs. The match for "US" is case-sensitive, so the
pronoun "us" doesn't count. Comments are kept without that filter because they belong to an
on-topic thread.

## Notes

- Follow each platform's terms of service and use the data only for research. Don't republish raw text.
- Reddit search returns at most ~250 results per query. That is why the scraper runs several
  narrow queries across many subreddits and removes duplicates.
- For history older than about a year, Reddit search won't reach back far enough. Use a Pushshift
  archive dump (e.g. Arctic Shift) instead.

## Analysis notebook

`US_India_Trade_Sentiment_Analysis.ipynb` (open in Google Colab) takes the scraped `x_all.csv` and runs:

1. **Cleaning:** collection window, exact and near-duplicates, posts over 1,000 characters, at most 3 posts per author.
2. **Part A, classic NLP:** TF-IDF keywords, VADER sentiment, a TF-IDF + Logistic Regression sentiment model, and NMF topics.
3. **Part B, LLM:** Google Gemini (free tier) labels every post (sentiment, topic, sarcasm, reason) with structured
   JSON output, then writes a summary of the community conversation. Needs a free API key from aistudio.google.com.
   It sends 50 posts per request, paces requests, and saves progress to `llm_labels.csv` after every request.
   If the free daily limit is reached, run the cell again later and it continues where it stopped.
4. **Part C, comparison:** sentiment mix by method, agreement and Cohen's kappa, confusion matrices,
   disagreement examples, NMF-vs-LLM topic match, and daily net sentiment.
5. **Insights and conclusion.**
