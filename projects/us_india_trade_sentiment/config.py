"""Search terms and sources for the US-India trade deal corpus."""

# Reddit search queries (Reddit search is OR-friendly but weak on phrases,
# so we run several short queries and dedupe afterwards).
REDDIT_QUERIES = [
    '"trade deal" India US',
    '"trade agreement" India America',
    "India US tariffs",
    "India tariff Trump",
    "Bilateral Trade Agreement India",
    "Indo-US trade",
    "Piyush Goyal trade",
    "India Russian oil tariff",
]

SUBREDDITS = [
    "india",
    "IndiaSpeaks",
    "unitedstatesofindia",
    "indianews",
    "IndianStockMarket",
    "IndiaInvestments",
    "IndiaTax",
    "worldnews",
    "geopolitics",
    "Economics",
    "economy",
    "neoliberal",
    "politics",
    "news",
]

# Also search all of Reddit (not restricted to a subreddit).
SEARCH_ALL_REDDIT = True

# X / Twitter API v2 query (recent search covers the last 7 days only).
X_QUERY = (
    '("trade deal" OR "trade agreement" OR "trade talks" OR tariff OR tariffs OR BTA) '
    "(India OR Indian OR Modi OR Goyal) "
    "(US OR USA OR America OR American OR Trump OR Washington) "
    "-is:retweet lang:en"
)

# Same search in X's web search syntax, used by the twscrape collector
# ("Latest" tab, so the newest tweets come first).
X_WEB_QUERY = (
    '("trade deal" OR "trade agreement" OR "trade talks" OR tariff OR tariffs OR BTA) '
    "(India OR Indian OR Modi OR Goyal) "
    "(US OR USA OR America OR American OR Trump OR Washington) "
    "lang:en -filter:retweets"
)

# Relevance filter applied to posts/tweets. A text must hit one term from each group
# (US group = US_TERMS or US_TERMS_CASED).
INDIA_TERMS = r"\b(india|indian|indians|modi|goyal|new delhi|delhi|bharat|indo)\b"
US_TERMS = r"\b(usa|america|american|trump|washington|lutnick|greer|ustr)\b"
# Matched case-sensitively so the pronoun "us" does not count.
US_TERMS_CASED = r"(\bUS\b|\bU\.S\.|\bUSA\b)"
TRADE_TERMS = r"\b(trade|tariffs?|deal|agreement|bta|exports?|imports?|duty|duties)\b"

# Time window for Reddit search: hour, day, week, month, year, all
REDDIT_TIME_FILTER = "year"
