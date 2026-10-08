import pandas as pd

from scrapers import reddit, twitter
from scrapers.common import clean_text, is_relevant, to_frame


def test_relevance_filter():
    assert is_relevant("US and India close in on a trade deal")
    assert is_relevant("Trump slaps 50% tariffs on Indian goods")
    assert not is_relevant("Let us talk about India's cricket team")  # pronoun "us"
    assert not is_relevant("India wins the trade of the century in IPL auction")  # no US term


def test_clean_text():
    assert clean_text("Tariffs &amp; deals  https://x.com/a\n\nok") == "Tariffs & deals ok"


def test_reddit_parsers():
    post = reddit.parse_post(
        {
            "id": "abc",
            "title": "India-US trade deal signed",
            "selftext": "",
            "created_utc": 1759800000,
            "author": "someone",
            "subreddit": "india",
            "score": 42,
            "num_comments": 2,
            "permalink": "/r/india/comments/abc/x/",
        },
        query="q",
    )
    assert post.kind == "post" and post.community == "india" and post.author_hash != "someone"

    tree = [
        {
            "kind": "t1",
            "data": {
                "id": "c1",
                "body": "Good for exporters",
                "author": "a",
                "score": 5,
                "created_utc": 1759800100,
                "permalink": "/r/india/comments/abc/x/c1/",
                "replies": {
                    "data": {
                        "children": [
                            {"kind": "t1", "data": {"id": "c2", "body": "[deleted]", "replies": ""}},
                            {"kind": "more", "data": {"children": ["c3"]}},
                        ]
                    }
                },
            },
        }
    ]
    comments = reddit.parse_comment_tree(tree, "abc", "india")
    assert [c.id for c in comments] == ["c1", "c2"]
    df = to_frame([post] + comments)
    assert list(df["id"]) == ["abc", "c1"]  # deleted comment dropped


def test_twitter_parser_and_export(tmp_path):
    payload = {
        "data": [
            {
                "id": "1",
                "text": "US India trade deal finally?",
                "author_id": "u1",
                "created_at": "2026-10-01T00:00:00Z",
                "public_metrics": {"like_count": 3, "reply_count": 1},
            }
        ],
        "includes": {"users": [{"id": "u1", "username": "alice"}]},
    }
    [t] = twitter.parse_tweets(payload)
    assert t.score == 3 and t.url.endswith("/alice/status/1")

    path = tmp_path / "export.csv"
    pd.DataFrame(
        [
            {"tweet_id": 9, "full_text": "Tariffs on India by Trump hurt trade", "likes": 7},
            {"tweet_id": 10, "full_text": "nice weather", "likes": 1},
        ]
    ).to_csv(path, index=False)
    recs = twitter.load_export(str(path))
    assert [r.id for r in recs] == ["9"] and recs[0].score == 7


def test_twscrape_parser():
    from datetime import datetime, timezone
    from types import SimpleNamespace

    t = SimpleNamespace(
        id=123,
        conversationId=120,
        date=datetime(2026, 10, 8, 9, 30, tzinfo=timezone.utc),
        user=SimpleNamespace(username="bob"),
        rawContent="Trump says India trade deal is close https://t.co/x",
        likeCount=12,
        replyCount=4,
        url="https://x.com/bob/status/123",
    )
    r = twitter.parse_twscrape_tweet(t, "q")
    assert (r.id, r.parent_id, r.score, r.num_replies) == ("123", "120", 12, 4)
    assert r.text == "Trump says India trade deal is close"
    assert r.created_utc.startswith("2026-10-08T09:30") and r.author_hash != "bob"


def test_twscrape_stops_at_max_tweets(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from types import SimpleNamespace

    twscrape = __import__("pytest").importorskip("twscrape")

    async def endless(self, q, limit=-1, kv=None):  # ignores `limit`, like real twscrape can
        i = 0
        while True:
            i += 1
            yield SimpleNamespace(
                id=i, conversationId=i, date=datetime.now(timezone.utc),
                user=SimpleNamespace(username="u"), rawContent="US India trade deal",
                likeCount=0, replyCount=0, url="u",
            )

    monkeypatch.setattr(twscrape.API, "search", endless)
    monkeypatch.setenv("X_USERNAME", "a")
    monkeypatch.setenv("X_COOKIES", "auth_token=x; ct0=y")
    recs = twitter.scrape_twscrape(max_tweets=150, db_path=str(tmp_path / "db"))
    assert len(recs) == 150
