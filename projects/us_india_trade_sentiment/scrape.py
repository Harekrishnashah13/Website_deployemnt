"""Collect US-India trade deal discussion from Reddit and X into one CSV.

Examples:
    python scrape.py                          # Reddit posts + comments, X if token set
    python scrape.py --no-x --max-threads 50  # quicker Reddit-only run
    python scrape.py --x-export tweets.csv    # add tweets from an export file
    python scrape.py --no-reddit --x-source twscrape --max-tweets 2000
    python scrape.py --no-reddit --x-source twscrape --x-every 30   # live: poll every 30 min
"""

import argparse
import os
import time

import pandas as pd
from dotenv import load_dotenv

from scrapers import reddit, twitter
from scrapers.common import save, to_frame


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/raw")
    ap.add_argument("--no-reddit", action="store_true")
    ap.add_argument("--no-comments", action="store_true", help="Reddit posts only")
    ap.add_argument("--max-pages", type=int, default=3, help="search pages (100 posts each) per query")
    ap.add_argument("--max-threads", type=int, default=200, help="threads to pull comments from")
    ap.add_argument("--no-x", action="store_true")
    ap.add_argument("--max-tweets", type=int, default=1000)
    ap.add_argument("--x-export", action="append", default=[], help="CSV/JSON tweet export (repeatable)")
    ap.add_argument("--x-source", choices=["api", "twscrape"], default="api",
                    help="api = official X API (X_BEARER_TOKEN); twscrape = your X login cookies")
    ap.add_argument("--x-query", help="override the X search query from config.py")
    ap.add_argument("--x-since", help="only tweets on/after YYYY-MM-DD (twscrape)")
    ap.add_argument("--x-every", type=float, metavar="MINUTES",
                    help="keep running and fetch new tweets every N minutes into x_live.csv")
    args = ap.parse_args()
    load_dotenv()

    frames = []
    if not args.no_reddit:
        recs = reddit.scrape(
            max_pages=args.max_pages,
            max_threads=args.max_threads,
            with_comments=not args.no_comments,
        )
        df = to_frame(recs)
        print(f"Reddit saved: {save(df, args.out, 'reddit')} ({len(df)} rows)")
        frames.append(df)
    if not args.no_x and args.x_every:
        watch_x(args)
        return
    if not args.no_x:
        recs = fetch_x(args)
        for path in args.x_export:
            recs += twitter.load_export(path)
        df = to_frame(recs)
        if len(df):
            print(f"X saved: {save(df, args.out, 'x')} ({len(df)} rows)")
            frames.append(df)

    if frames:
        corpus = pd.concat(frames, ignore_index=True)
        print(f"Combined corpus: {save(corpus, args.out, 'corpus')} ({len(corpus)} rows)")
        print(corpus.groupby(["platform", "kind"]).size().to_string())


def fetch_x(args):
    if args.x_source == "twscrape":
        return twitter.scrape_twscrape(args.x_query, max_tweets=args.max_tweets, since=args.x_since)
    return twitter.scrape(args.x_query, max_tweets=args.max_tweets)


def watch_x(args):
    """Poll X repeatedly, appending only tweets not seen before. Stop with Ctrl+C."""
    path = os.path.join(args.out, "x_live.csv")
    os.makedirs(args.out, exist_ok=True)
    seen = set(pd.read_csv(path, usecols=["id"], dtype=str)["id"]) if os.path.exists(path) else set()
    print(f"Live mode: appending to {path} every {args.x_every:g} min ({len(seen)} tweets so far)")
    while True:
        df = to_frame(fetch_x(args))
        new = df[~df["id"].astype(str).isin(seen)]
        if len(new):
            new.to_csv(path, mode="a", header=not os.path.exists(path), index=False)
            seen.update(new["id"].astype(str))
        print(f"{time.strftime('%H:%M')} +{len(new)} new tweets, {len(seen)} total")
        time.sleep(args.x_every * 60)


if __name__ == "__main__":
    main()
