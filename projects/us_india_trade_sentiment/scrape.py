"""Collect US-India trade deal discussion from Reddit and X into one CSV.

Examples:
    python scrape.py                          # Reddit posts + comments, X if token set
    python scrape.py --no-x --max-threads 50  # quicker Reddit-only run
    python scrape.py --x-export tweets.csv    # add tweets from an export file
"""

import argparse

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
    if not args.no_x:
        recs = twitter.scrape(max_tweets=args.max_tweets)
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


if __name__ == "__main__":
    main()
