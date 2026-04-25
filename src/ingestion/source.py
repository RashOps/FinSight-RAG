RSS_FEEDS = {

    # ═══════════════════════════════════
    # SOURCES FIABLES & TESTÉES (9/16)
    # ═══════════════════════════════════

    # MarketWatch (Dow Jones)
    "marketwatch_top":       "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines",
    "marketwatch_markets":   "https://feeds.content.dowjones.io/public/rss/mw_marketpulse",
    "MarketWatch Top Stories": "http://feeds.marketwatch.com/marketwatch/topstories/",

    # Investing.com
    "investing_com":         "https://www.investing.com/rss/news.rss",
    "Investing.com":         "https://fr.investing.com/rss/news_25.rss",

    # Bloomberg
    "Bloomberg Markets":     "https://feeds.bloomberg.com/markets/news.rss",
    "Bloomberg Economics":   "https://feeds.bloomberg.com/economics/news.rss",

    # Institutions financières
    "ecb_press":             "https://www.ecb.europa.eu/rss/press.html",
    "fed_press":             "https://www.federalreserve.gov/feeds/press_all.xml",

    # ═══════════════════════════════════
    # SOURCES PROBLÉMATIQUES (7/16)
    # ═══════════════════════════════════

    # CNBC - HTTP 403 (bloque les bots)
    # "cnbc_top":          "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    # "cnbc_world":        "https://www.cnbc.com/id/100727362/device/rss/rss.html",
    # "cnbc_finance":      "https://www.cnbc.com/id/10000664/device/rss/rss.html",
    # "cnbc_earnings":     "https://www.cnbc.com/id/15839135/device/rss/rss.html",

    # Yahoo Finance - HTTP 429 (rate limiting)
    # "yahoo_finance":     "https://finance.yahoo.com/news/rssindex",
    # "yahoo_top_stories": "https://finance.yahoo.com/rss/topstories",

    # SEC - HTTP 403 (bloque les bots)
    # "sec_press":         "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=&dateb=&owner=include&count=40&search_text=&output=atom",

}