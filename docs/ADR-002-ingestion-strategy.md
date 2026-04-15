# ADR 002 : Stratégie d'Ingestion, Optimisation des Ressources et Modèle de Données

## 1. Statut
**Accepté** (2026-04-10)

## 2. Contexte
Le moteur RAG (FinSight_RAG) nécessite une base de connaissances riche (Full-Text) extraite de l'actualité financière. Cependant, le pipeline d'extraction, de nettoyage et de vectorisation est lourd en I/O et en CPU/RAM. L'infrastructure cible de l'API (Free Tier, 512 MB RAM) impose des contraintes strictes pour éviter les `Time-Outs` HTTP et les crashs `OOMKill` (Out of Memory). De plus, la qualité de la donnée ingérée détermine la qualité des réponses du LLM.

## 3. Décisions

### 3.1. Découplage de l'Ingestion (CI/CD vs Serveur)
* **Décision :** Rejet de `apscheduler` au sein de l'API FastAPI. Le pipeline d'ingestion (`collector.py` et `vectorizer.py`) sera exécuté par des **GitHub Actions** via des tâches Cron.
* **Justification :** Protège le serveur FastAPI (Single vCPU) de la charge de scraping et de calcul d'embeddings. Les serveurs de GitHub assumeront la charge de calcul (gratuitement), garantissant une haute disponibilité de l'API de *Serving*.

### 3.2. Extraction de Texte (Scraping)
* **Décision :** Utilisation du combo `feedparser` + `trafilatura`. Rejet des sources sous Paywall strict (ex: Financial Times, WSJ).
* **Justification :** `trafilatura` garantit une extraction propre du *Full-Text* sans boilerplate (menus, pubs). Se limiter aux sources ouvertes (Reuters, Yahoo Finance, Investing.com) évite d'indexer des messages d'erreur ou des paywalls qui feraient halluciner le RAG.

### 3.3. Abandon de la NER à l'Ingestion
* **Décision :** Rejet de la librairie `spacy` pour l'extraction d'entités nommées lors de la phase d'ingestion.
* **Justification :** Le modèle NLP de `spacy` consomme trop de RAM pour notre environnement contraint. La reconnaissance d'entités (Entreprises, Tickers, Personnes) sera déléguée au LLM (Groq/Llama-3) au moment de la requête utilisateur (Inférence).

### 3.4. Les API Freemium comme "Agent Tools"
* **Décision :** Les API comme Alpha Vantage, Finnhub ou NewsAPI ne seront **pas** utilisées pour populer la base vectorielle. Elles seront intégrées plus tard en tant que `Tools` (LlamaIndex) appelables dynamiquement par le LLM.
* **Justification :** Évite de diluer le Vector Store avec des *snippets* (textes courts/résumés) de faible valeur sémantique. Permet à l'agent de croiser une recherche sémantique (via Qdrant) avec une recherche de prix exacte en temps réel (via Tool calling).

### 3.5. Modèle de Données (State Machine)
* **Décision :** Mise en place d'un payload MongoDB orienté "Machine à état" avec un système de déduplication natif.
* **Structure du Data Contract :**
  ```json
  {
      "_id": "sha256(url)",              // Déduplication absolue de l'URL
      "source": "reuters",
      "title": "Fed raises rates...",
      "title_hash": "fedraisesrates...", // Déduplication cross-source (syndication)
      "summary": "...",
      "content": "Full text...",         // Cœur du RAG
      "url": "https://...",
      "published_at": "ISODate(...)",    // Pour le TTL (Time-To-Live)
      "language": "en",              
      "vectorized": false,               // Flag d'état pour le vectorizer.py
      "vectorized_at": null,
      "qdrant_chunk_ids": []             // UUIDs des chunks correspondants
  }