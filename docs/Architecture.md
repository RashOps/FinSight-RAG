# Architecture - FinSight RAG

## Vue d'Ensemble

FinSight_RAG est un moteur RAG (Retrieval-Augmented Generation) spécialisé dans l'analyse de contenu financier. L'architecture suit un design découplé basé sur plusieurs services externes pour optimiser les ressources sur infrastructure contrainte (Free Tier: 1 vCPU, 512 MB RAM).

## Stack Technique

### Core Framework
- **FastAPI** (>=0.135.3): Framework web asynchrone pour l'API
- **Uvicorn** (>=0.44.0): Serveur ASGI pour déploiement production
- **Pydantic** (>=2.12.5): Validation des schémas et configuration

### Orchestration & RAG
- **LlamaIndex** (>=0.14.16): Framework orchestration pour le RAG
  - Ingestion de données
  - Stratégies de chunking intelligentes
  - Gestion du QueryEngine
- **Groq LLM** (via `llama-index-llms-groq`): Inférence ultra-rapide (>800 tokens/sec)
  - Modèle: Llama-3
  - Technologie: LPU (Language Processing Units)
- **Cohere Embeddings** (via `llama-index-embeddings-cohere`): Modèle `embed-multilingual-v3.0`
  - Support multilingue
  - Offloading du calcul matriciel

### Storage & Vectorisation
- **Qdrant Cloud** (via `llama-index-vector-stores-qdrant`): Base de données vectorielle
  - Stockage remote des embeddings
  - Évite la consommation RAM locale
  - Traitement et recherche ultra-rapides
- **MongoDB** (>=4.16.0): Base de données source des documents
  - Stockage des documents bruts
  - Métadonnées associées

### Storage Characteristics
- **Vector DB** : Qdrant Cloud.
- **Embeddings** : all-MiniLM-L6-v2 (Or with sentence-transformers library in local).
- **Dimensionalité** : 384.
- **Métrique de distance** : Cosine.

### Infrastructure & Déploiement
- **Docker** (lightweight image `python:3.12-slim`)
- **Cibles**: Koyeb ou Render (Free Tier)
- **CI/CD**: GitHub Actions (tests + déploiement automatisé)

### Monitoring & Observabilité
- **Langfuse/Arize Phoenix**: Tracing des requêtes
  - Identification de la source d'erreur (Qdrant vs hallucination LLM)
- **Logger personnalisé**: Logs rotatifs (5 fichiers x 5MB)

### Testing & Quality
- **pytest** (>=9.0.3): Framework de tests
- **pytest-cov** (>=7.1.0): Couverture de code
- **httpx** (>=0.28.1): Tests d'intégration API

## Structure du Projet

```
FinSight_RAG/
├── docs/
│   ├── ADR-001-stack-technique.md       # Décisions architecturales
│   └── ADR-002-ingestion-strategy.md
│
├── src/
│   ├── config.py                         # Validation centralisée des env vars
│   │
│   ├── api/                              # Couche Serving (FastAPI)
│   │   ├── main.py                       # Point d'entrée de l'application
│   │   └── schemas.py                    # Contrats Pydantic (Input/Output)
│   │
│   ├── rag/                              # Cerveau du RAG (LlamaIndex)
│   │   ├── engine.py                     # QueryEngine (Groq + Cohere)
│   │   └── prompts.py                    # Templates strictement guidés
│   │
│   ├── ingestion/                        # Pipeline d'ingestion des données
│   │   ├── collector.py                  # Fetch article in mongoDB
│   │   ├── source.py                     # RSS source Link
│   │   └── vectorizer.py                 # ETL: MongoDB -> Chunking -> Qdrant
│   │
│   └── utils/                            # Utilitaires partagés
│       ├── db_client.py                  # Client MongoDB
│       ├── date_parser.py                # Parsing des dates des articles
│       └── logger.py                     # Logger centralisé (RotatingFileHandler)
│
├── tests/
│   ├── unit/                             # Tests unitaires
│   │   └── (Tests de chunking, retrieval)
│   └── integration/                      # Tests d'intégration
│       └── (Tests API avec httpx)
│
├── logs/                                 # Logs applicatifs (ignoré par git)
│   └── app.log
│
├── Dockerfile                            # Image Docker pour déploiement
├── pyproject.toml                        # Configuration du projet (PEP 517/518)
├── uv.lock                               # Lock file (UV package manager)
├── README.md                             # Documentation utilisateur
├── .env.exemple                          # Template des variables d'environnement
└── .gitignore                            # Exclusions git (.venv/, logs/, .env)
```

## Flux Architectural

### 1. Pipeline d'Ingestion (Batch)
```
Source (MongoDB)
    ↓
[indexer.py] Extraction des documents
    ↓
LlamaIndex Chunking
    ↓
Cohere Embeddings API
    ↓
Qdrant Cloud Vector Store
```

**Composant acteur**: `src/ingestion/indexer.py`
- Requête MongoDB pour extraire les documents financiers
- Segmentation intelligente du texte (LlamaIndex splitter)
- Génération des embeddings (appel API Cohere)
- Indexation dans Qdrant

### 2. Pipeline de Requête (Real-time)
```
Client HTTP
    ↓
[main.py] Route FastAPI
    ↓
Request validation (Pydantic schemas)
    ↓
[engine.py] RAG Query
    ├→ Cohere Embeddings (embed query)
    ├→ Qdrant Retrieval (top-k vecteurs similaires)
    ├→ Document context assembly
    └→ Groq LLM Inference (response generation)
    ↓
[schemas.py] Response marshalling
    ↓
JSON Response
```

**Composants acteurs**: 
- `src/api/main.py`: Routeur et point d'entrée
- `src/rag/engine.py`: Orchestration LlamaIndex QueryEngine
- `src/api/schemas.py`: Validation et sérialisation des requêtes/réponses

### 3. Architecture Complète (End-to-End)

```
┌─────────────────┐
│   Client App    │
└────────┬────────┘
         │ HTTP(S)
         ▼
┌─────────────────────────────────┐
│   FastAPI (src/api/main.py)     │────────────┐
│  - Route Handler                 │            │
│  - Request Validation (Pydantic) │            │
└────────┬────────────────────────┘            │
         │                                      │
         │ Sync/Async calls                     │
         ▼                                      │
┌─────────────────────────────────┐            │
│   RAG Engine (src/rag)           │            │
│  - LlamaIndex QueryEngine        │            │
│  - Prompt Templates (prompts.py) │            │
│  - Context Assembly              │            │
└────┬────────┬──────────┬─────────┘            │
     │        │          │                      │
  API│     API│       API│                      │
     │        │          │                      │
     ▼        ▼          ▼                      ▼
┌────────┐ ┌────────┐ ┌──────────┐  ┌──────────────┐
│ Cohere │ │ Groq   │ │ Qdrant   │  │  MongoDB     │
│Embedds │ │  LLM   │ │ Vector   │  │ (source data)│
│        │ │        │ │ DB Cloud │  │              │
└────────┘ └────────┘ └──────────┘  └──────────────┘
  External External  External        External
  API      API       API             API/Service
```

## Flux de Données

### Configuration & Démarrage
1. **Variables d'environnement** (`.env`) → `config.py` (Pydantic validation)
2. **Logger centralisé** (`utils/logger.py`) initialisé
3. **Clients APIs** créés (Groq, Cohere, Qdrant, MongoDB)
4. **FastAPI app** lancée via Uvicorn

### Ingestion (Command/Batch)
1. `indexer.py` se connecte à MongoDB
2. Fetch documents avec leurs métadonnées
3. LlamaIndex chunking (Document splitting)
4. Appel API Cohere pour embeddings
5. Stockage dans Qdrant Cloud

### Requête (Query-time)
1. Client POST `/query` avec la question
2. Validation Pydantic (`schemas.QueryRequest`)
3. `engine.py` crée un QueryEngine LlamaIndex
4. Sub-étapes:
   - Embedding de la requête (Cohere)
   - Recherche vectorielle dans Qdrant (top-k résultats)
   - Assemblage du contexte
   - Prompt injection dans template (prompts.py)
   - Inférence via Groq LLM
5. Response marshalling et sérialisation JSON
6. Return à client

## Choix Architecturaux Clés

| Composant | Choix | Justification |
|-----------|-------|---------------|
| **Orchestration** | LlamaIndex | Chunking et indexing supérieurs vs LangChain |
| **Vector DB** | Qdrant Cloud | Remote storage → évite OOMKill sur RAM limitée |
| **Embeddings** | Cohere multilingual | Offloading calcul, support multilingue |
| **LLM** | Groq (Llama-3) | 800+ tokens/sec, Free Tier, OpenAI-compatible |
| **Web Framework** | FastAPI | Async, rapide, validation native Pydantic |
| **Infra** | Docker + Koyeb/Render | Léger, scalable, Free Tier, CI/CD GitHub Actions |
| **DB Source** | MongoDB | Schéma flexible pour données financières |

## Production Readiness

### Déploiement
- ✅ **Docker image** optimisée (`python:3.12-slim`)
- ✅ **CI/CD** GitHub Actions (tests + build + push)
- ✅ **Hosting** Koyeb/Render (Free Tier compatible)
- ⏳ **CORS & Security headers** à configurer en production

### Observabilité
- ✅ **Logging rotatif** (5 fichiers x 5 MB)
- ✅ **Langfuse/Phoenix** pour tracing des hallucinations
- ⏳ **Healthchecks** API endpoints à ajouter

### Gestion des Erreurs
- ⚠️ **Network resilience**: Gestion des timeouts Groq/Qdrant requis (`httpx.TimeoutException`)
- ⚠️ **Circuit breaker** possible pour services externes
- ⚠️ **Rate limiting** des APIs externes

### Test Coverage
- ✅ **pytest** configuré
- ✅ **httpx** pour tests d'intégration
- ⏳ **Coverage minimale** à définir (80%+ recommandé)