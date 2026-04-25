### Fast Ideas

FEEDS = {
    "yahoo_finance": "https://finance.yahoo.com/rss/topstories",
    "reuters_business": "https://feeds.reuters.com/reuters/businessNews",
    "marketwatch": "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines",
    "investing_com": "https://www.investing.com/rss/news.rss",
    "seekingalpha": "https://seekingalpha.com/feed.xml",
    "ft": "https://www.ft.com/rss/home",
    "reuters":       "https://feeds.reuters.com/reuters/businessNews",
    "yahoo_finance": "https://finance.yahoo.com/rss/topstories",
    "marketwatch":   "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines",
    "ft":            "https://www.ft.com/rss/home",
    "wsj_markets":   "https://feeds.content.dowjones.io/public/rss/WSJcomUSBusiness",
}


API freenium - Utilisé pour enrichir notre base de données
NewsAPI.org
Alpha Vantage News
Finnhub
TheNewsAPI
Yahoo (ttps://query1.finance.yahoo.com/v1/finance/search / ttps://query2.finance.yahoo.com/v1/finance/search)


Lib Python - Outils a analyser
httpx
trafilatura
apscheduler (Pour rendre le pipeline automatique chaque jour - A voir)
langdetect (pour detecter la langue)
feedparser (pour parser plus facilement)
BeautifulSoup4 (pour le parsing)
Spacy : Pour faire Name Entities Recognition


Stratégie
Purger les articles vectorisés après 2 semaines
Un fois vectorisé, réecrire le payload sur le lui-même grace au tag (vectorized)
Stratégie pour gerer les memes articles qui apparaissent sur plusieurs site (penser a mettre un hash sur le titre)


Payload - Document MongoDB — chaque news
{
    "_id": "sha256(url)",          # déduplication native
    "source": "reuters",
    "title": "Fed raises rates...",
    "summary": "The Federal Reserve...",
    "url": "https://...",
    "published_at": ISODate("2025-04-10T08:00:00Z"),
    "Entities": [values, ...]       # Extract with spacy
    "language": "en",              # détecté auto (langdetect)
    "vectorized": False,           # flag de processing !!
    "vectorized_at": None,
    "qdrant_id": None,             # lien vers le point Qdrant
    "embedding_model": None,       # "cohere/embed-v4.0"
}