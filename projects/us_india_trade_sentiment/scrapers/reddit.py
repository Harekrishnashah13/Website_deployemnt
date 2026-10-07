"""Reddit scraper: search posts, then pull each thread's comment tree.

Uses Reddit's JSON endpoints. With REDDIT_CLIENT_ID/SECRET set it authenticates
(app-only OAuth, ~100 requests/min); without them it falls back to the public
endpoints (~10 requests/min, and Reddit may block anonymous traffic).
"""

import os
import time

import requests

import config
from scrapers.common import Record, clean_text, hash_author, is_relevant, to_iso

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"


class RedditClient:
    def __init__(self, user_agent=None):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent or os.getenv(
            "REDDIT_USER_AGENT", "us-india-trade-sentiment/0.1"
        )
        cid, secret = os.getenv("REDDIT_CLIENT_ID"), os.getenv("REDDIT_CLIENT_SECRET")
        if cid and secret:
            resp = self.session.post(
                TOKEN_URL,
                auth=(cid, secret),
                data={"grant_type": "client_credentials"},
                timeout=30,
            )
            resp.raise_for_status()
            self.session.headers["Authorization"] = f"bearer {resp.json()['access_token']}"
            self.base = "https://oauth.reddit.com"
            self.delay = 0.7
        else:
            self.base = "https://www.reddit.com"
            self.delay = 6.5
        self.authenticated = self.base.startswith("https://oauth")

    def get(self, path, params=None, retries=4):
        url = self.base + path + ("" if self.authenticated else ".json")
        for attempt in range(retries):
            time.sleep(self.delay)
            resp = self.session.get(url, params={**(params or {}), "raw_json": 1}, timeout=30)
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = float(resp.headers.get("x-ratelimit-reset", 2 ** (attempt + 2)))
                print(f"  reddit {resp.status_code}, waiting {wait:.0f}s")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            remaining = float(resp.headers.get("x-ratelimit-remaining", 10))
            if remaining < 2:
                time.sleep(float(resp.headers.get("x-ratelimit-reset", 60)))
            return resp.json()
        resp.raise_for_status()


def parse_post(data, query=""):
    title = clean_text(data.get("title", ""))
    return Record(
        platform="reddit",
        kind="post",
        id=data["id"],
        parent_id="",
        created_utc=to_iso(data.get("created_utc")),
        author_hash=hash_author(data.get("author")),
        community=data.get("subreddit", ""),
        title=title,
        text=clean_text(data.get("selftext", "")),
        score=int(data.get("score") or 0),
        num_replies=int(data.get("num_comments") or 0),
        url="https://www.reddit.com" + data.get("permalink", ""),
        query=query,
    )


def parse_comment_tree(children, post_id, subreddit, out=None):
    """Flatten a comment listing; 'more' stubs are skipped."""
    out = [] if out is None else out
    for child in children:
        if child.get("kind") != "t1":
            continue
        d = child["data"]
        out.append(
            Record(
                platform="reddit",
                kind="comment",
                id=d["id"],
                parent_id=post_id,
                created_utc=to_iso(d.get("created_utc")),
                author_hash=hash_author(d.get("author")),
                community=subreddit,
                title="",
                text=clean_text(d.get("body", "")),
                score=int(d.get("score") or 0),
                num_replies=0,
                url="https://www.reddit.com" + d.get("permalink", ""),
                query="",
            )
        )
        replies = d.get("replies")
        if isinstance(replies, dict):
            parse_comment_tree(replies["data"]["children"], post_id, subreddit, out)
    return out


def search_posts(client, query, subreddit=None, max_pages=3, time_filter=None):
    path = f"/r/{subreddit}/search" if subreddit else "/search"
    params = {
        "q": query,
        "sort": "relevance",
        "t": time_filter or config.REDDIT_TIME_FILTER,
        "limit": 100,
        "type": "link",
    }
    if subreddit:
        params["restrict_sr"] = 1
    posts, after = [], None
    for _ in range(max_pages):
        if after:
            params["after"] = after
        listing = client.get(path, params)["data"]
        posts += [parse_post(c["data"], query) for c in listing["children"] if c["kind"] == "t3"]
        after = listing.get("after")
        if not after:
            break
    return posts


def fetch_comments(client, post, limit=500):
    data = client.get(f"/comments/{post.id}", {"limit": limit, "sort": "top", "depth": 8})
    return parse_comment_tree(data[1]["data"]["children"], post.id, post.community)


def scrape(max_pages=3, max_threads=200, min_comments=3, with_comments=True):
    client = RedditClient()
    print(f"Reddit: {'OAuth' if client.authenticated else 'anonymous'} mode")

    targets = [None] if config.SEARCH_ALL_REDDIT else []
    targets += config.SUBREDDITS
    posts = {}
    for sub in targets:
        for q in config.REDDIT_QUERIES:
            try:
                found = search_posts(client, q, sub, max_pages=max_pages)
            except requests.HTTPError as e:
                print(f"  skip r/{sub or 'all'} '{q}': {e}")
                continue
            kept = [p for p in found if is_relevant(f"{p.title} {p.text}")]
            for p in kept:
                posts.setdefault(p.id, p)
            print(f"  r/{sub or 'all'} '{q}': {len(found)} found, {len(kept)} relevant")

    records = list(posts.values())
    if with_comments:
        # Busiest threads first: they carry most of the discussion.
        threads = sorted(
            (p for p in posts.values() if p.num_replies >= min_comments),
            key=lambda p: p.num_replies,
            reverse=True,
        )[:max_threads]
        for i, p in enumerate(threads, 1):
            try:
                comments = fetch_comments(client, p)
            except requests.HTTPError as e:
                print(f"  skip comments of {p.id}: {e}")
                continue
            records += comments
            print(f"  [{i}/{len(threads)}] {p.id} r/{p.community}: {len(comments)} comments")
    return records
