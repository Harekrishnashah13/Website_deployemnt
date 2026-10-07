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
