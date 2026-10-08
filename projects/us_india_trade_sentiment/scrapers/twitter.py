"""X / Twitter collection.

Three routes:
  1. scrape(): official API v2 recent search (last 7 days). Needs X_BEARER_TOKEN
     on a tier that includes search (Basic or higher; Free has no search).
  2. scrape_twscrape(): X's own web search via twscrape, logged in with the cookies
     of your X account (X_USERNAME + X_COOKIES). Free, but against X's terms of
     service, so use a spare account: X can lock accounts that scrape.
  3. load_export(): normalise a CSV/JSON export you collected elsewhere
     (e.g. an Apify/X-export dataset, or tweets saved by hand) into the same schema.
"""

import asyncio
import os
import time

import pandas as pd
import requests

import config
from scrapers.common import Record, clean_text, hash_author, is_relevant

SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"


def parse_tweets(payload, query=""):
    users = {u["id"]: u.get("username", "") for u in payload.get("includes", {}).get("users", [])}
    out = []
    for t in payload.get("data", []):
        m = t.get("public_metrics", {})
        username = users.get(t.get("author_id"), "")
        out.append(
            Record(
                platform="x",
                kind="tweet",
                id=t["id"],
                parent_id=t.get("conversation_id", ""),
                created_utc=t.get("created_at", ""),
                author_hash=hash_author(username or t.get("author_id", "")),
                community="",
                title="",
                text=clean_text(t.get("text", "")),
                score=int(m.get("like_count", 0)),
                num_replies=int(m.get("reply_count", 0)),
                url=f"https://x.com/{username or 'i'}/status/{t['id']}",
                query=query,
            )
        )
    return out


def scrape(query=None, max_tweets=1000):
    token = os.getenv("X_BEARER_TOKEN")
    if not token:
        print("X: no X_BEARER_TOKEN set, skipping (use --x-export to load a file instead)")
        return []
    query = query or config.X_QUERY
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "query": query,
        "max_results": 100,
        "tweet.fields": "created_at,public_metrics,lang,conversation_id,author_id",
        "expansions": "author_id",
        "user.fields": "username",
    }
    records = []
    while len(records) < max_tweets:
        resp = requests.get(SEARCH_URL, headers=headers, params=params, timeout=30)
        if resp.status_code == 429:
            reset = int(resp.headers.get("x-rate-limit-reset", time.time() + 900))
            wait = max(reset - time.time(), 5)
            print(f"  X rate limited, waiting {wait:.0f}s")
            time.sleep(wait)
            continue
        if resp.status_code in (401, 403):
            print(f"  X {resp.status_code}: {resp.text[:200]}")
            print("  Your token/tier probably lacks search access.")
            break
        resp.raise_for_status()
        payload = resp.json()
        batch = parse_tweets(payload, query)
        records += batch
        print(f"  X: +{len(batch)} tweets ({len(records)} total)")
        next_token = payload.get("meta", {}).get("next_token")
        if not next_token:
            break
        params["next_token"] = next_token
        time.sleep(1.1)
    return [r for r in records[:max_tweets] if is_relevant(r.text)]


def parse_twscrape_tweet(t, query=""):
    """twscrape Tweet object -> Record."""
    return Record(
        platform="x",
        kind="tweet",
        id=str(t.id),
        parent_id=str(t.conversationId or ""),
        created_utc=t.date.isoformat(),
        author_hash=hash_author(t.user.username),
        community="",
        title="",
        text=clean_text(t.rawContent),
        score=int(t.likeCount or 0),
        num_replies=int(t.replyCount or 0),
        url=t.url,
        query=query,
    )


async def _twscrape_search(query, max_tweets, db_path):
    from twscrape import API  # optional dependency

    api = API(db_path)
    username, cookies = os.getenv("X_USERNAME"), os.getenv("X_COOKIES")
    if username and cookies:
        accounts = {a.username for a in await api.pool.get_all()}
        if username not in accounts:
            await api.pool.add_account_cookies(username, cookies)
    records = []
    async for t in api.search(query, limit=max_tweets):
        records.append(parse_twscrape_tweet(t, query))
        if len(records) % 100 == 0:
            print(f"  X: {len(records)} tweets")
    return records


def scrape_twscrape(query=None, max_tweets=1000, since=None, db_path="data/twscrape_accounts.db"):
    """Search X's "Latest" tab. `since` is an optional YYYY-MM-DD lower bound."""
    if not (os.getenv("X_USERNAME") and os.getenv("X_COOKIES")) and not os.path.exists(db_path):
        print("X: set X_USERNAME and X_COOKIES (see README) to use twscrape, skipping")
        return []
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    query = query or config.X_WEB_QUERY
    if since:
        query += f" since:{since}"
    records = asyncio.run(_twscrape_search(query, max_tweets, db_path))
    print(f"  X: {len(records)} tweets fetched")
    return [r for r in records if is_relevant(r.text)]


# Column names used by common export tools, mapped to our schema.
_ALIASES = {
    "id": ["id", "id_str", "tweet_id", "tweetId"],
    "text": ["text", "full_text", "fullText", "content", "tweet"],
    "created_utc": ["created_at", "createdAt", "date", "timestamp"],
    "author": ["username", "user_screen_name", "author", "author.userName", "screen_name"],
    "score": ["like_count", "likeCount", "favorite_count", "likes"],
    "num_replies": ["reply_count", "replyCount", "replies"],
    "url": ["url", "twitterUrl", "tweet_url", "link"],
}


def _pick(row, names, default=""):
    for n in names:
        if n in row and pd.notna(row[n]):
            return row[n]
    return default


def load_export(path):
    df = pd.read_json(path) if path.endswith(".json") else pd.read_csv(path)
    df = pd.json_normalize(df.to_dict("records"))
    records = []
    for row in df.to_dict("records"):
        text = clean_text(str(_pick(row, _ALIASES["text"])))
        tid = str(_pick(row, _ALIASES["id"]))
        records.append(
            Record(
                platform="x",
                kind="tweet",
                id=tid,
                parent_id="",
                created_utc=str(_pick(row, _ALIASES["created_utc"])),
                author_hash=hash_author(str(_pick(row, _ALIASES["author"]))),
                community="",
                title="",
                text=text,
                score=int(_pick(row, _ALIASES["score"], 0) or 0),
                num_replies=int(_pick(row, _ALIASES["num_replies"], 0) or 0),
                url=str(_pick(row, _ALIASES["url"])),
                query=f"export:{os.path.basename(path)}",
            )
        )
    return [r for r in records if is_relevant(r.text)]
