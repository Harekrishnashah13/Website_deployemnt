"""Shared record schema, cleaning, relevance filter and saving."""

import hashlib
import html
import os
import re
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone

import pandas as pd

import config

# One row per post, comment or tweet. Every scraper emits this shape so the
# TF-IDF and LLM stages can treat both platforms the same way.
@dataclass
class Record:
    platform: str          # "reddit" | "x"
    kind: str              # "post" | "comment" | "tweet"
    id: str
    parent_id: str         # thread/post id for comments, conversation id for tweets
    created_utc: str       # ISO 8601
    author_hash: str
    community: str         # subreddit name, or "" for X
    title: str
    text: str
    score: int             # upvotes / likes
    num_replies: int
    url: str
    query: str             # the search that found it ("" for comments fetched by thread)


COLUMNS = [f.name for f in fields(Record)]

_URL_RE = re.compile(r"https?://\S+")
_WS_RE = re.compile(r"\s+")
_INDIA_RE = re.compile(config.INDIA_TERMS, re.I)
_US_RE = re.compile(config.US_TERMS, re.I)
_US_CASED_RE = re.compile(config.US_TERMS_CASED)
_TRADE_RE = re.compile(config.TRADE_TERMS, re.I)


def hash_author(name):
    if not name or name in ("[deleted]", "AutoModerator"):
        return name or ""
    salt = os.getenv("AUTHOR_HASH_SALT", "")
    return hashlib.sha256((salt + name).encode()).hexdigest()[:16]


def to_iso(ts):
    """Unix seconds or ISO string -> ISO 8601 UTC string."""
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    return ts or ""


def clean_text(text):
    """Light cleaning that keeps the wording intact for sentiment work."""
    if not text:
        return ""
    text = html.unescape(text)
    text = _URL_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def is_relevant(text):
    has_us = bool(_US_RE.search(text) or _US_CASED_RE.search(text))
    return bool(_INDIA_RE.search(text)) and has_us and bool(_TRADE_RE.search(text))


def is_junk(text):
    return text in ("", "[deleted]", "[removed]") or len(text) < 3


def to_frame(records):
    df = pd.DataFrame([asdict(r) for r in records], columns=COLUMNS)
    if df.empty:
        return df
    df = df[~df["text"].map(is_junk) | (df["title"] != "")]
    return df.drop_duplicates(subset=["platform", "id"]).reset_index(drop=True)


def save(df, out_dir, name):
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    path = os.path.join(out_dir, f"{name}_{stamp}.csv")
    df.to_csv(path, index=False)
    return path
