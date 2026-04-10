FinSight_RAG/
├── docs/
│   └── ADR-001-stack-technique.md   # Ton document de décision
├── src/
│   ├── api/                         # La couche Serving (FastAPI)
│   │   ├── main.py                  # Point d'entrée de l'API
│   │   └── schemas.py               # Contrats Pydantic (Input/Output)
│   ├── rag/                         # Le "Cerveau" LlamaIndex
│   │   ├── engine.py                # Configuration du QueryEngine (Groq/Cohere)
│   │   └── prompts.py               # Templates stricts pour limiter les hallucinations
│   ├── ingestion/                   # Le "Data Pipeline"
│   │   └── indexer.py               # Extrait Mongo -> Chunking -> Pousse vers Qdrant
│   └── config.py                    # Validation centralisée des variables d'environnement
├── tests/
│   ├── integration/                 # Tests de l'API avec httpx
│   └── unit/                        # Tests de la logique de chunking/retrieval
├── .env                             # Tes secrets (À mettre IMMÉDIATEMENT dans le .gitignore)
├── .gitignore
├── Dockerfile                       # Pour le déploiement futur sur Koyeb/Render
├── pyproject.toml
└── uv.lock