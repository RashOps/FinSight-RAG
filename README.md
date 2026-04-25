# FinSight RAG

[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![CI/CD](https://github.com/RashOps/finsight-rag/actions/workflows/ingestion.yml/badge.svg)](https://github.com/Rashops/finsight-rag/actions/workflows/ingestion.yml)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](Dockerfile)

FinSight RAG est un moteur de génération assistée par récupération (RAG) conçu pour synthétiser et répondre à des questions financières à partir de contenus documentaires et de flux de données.

Ce projet a pour objectif de proposer une architecture légère et résiliente, pensée pour fonctionner dans des environnements contraints (Free Tier, 1 vCPU, 512 MB RAM), tout en conservant des garanties de qualité de réponse et de contrôle des hallucinations.

Il repose sur une séparation claire des responsabilités :
- ingestion et indexation des données financières,
- stockage vectoriel déporté pour les embeddings,
- orchestration de la recherche et de la génération via LlamaIndex,
- exposition d'une API FastAPI pour les requêtes en temps réel.

Le dépôt est destiné à servir de base à un service RAG financier capable de répondre en langage naturel à des demandes analytiques et de veille, tout en gardant une infrastructure simple et maintenable.

## 🚀 Déploiement

<!-- TODO: Ajouter le lien de déploiement une fois disponible -->
<!-- [🌐 Application déployée](https://your-deployment-url.com) -->

## 📋 Prérequis

- **Python** >= 3.12
- **UV** (gestionnaire de paquets Python)
- **MongoDB** (base de données source)
- **Qdrant Cloud** (base de données vectorielle)
- **Cohere API/sentence-transformers/all-minilm-l6-v2** (embeddings)
- **Groq API** (LLM)

## 🛠️ Installation

### 1. Cloner le dépôt

```bash
git clone https://github.com/your-username/finsight-rag.git
cd finsight-rag
```

### 2. Installer les dépendances

```bash
# Avec UV (recommandé)
uv sync

# Ou avec pip (alternative)
pip install -e .
```

### 3. Configuration des variables d'environnement

Copiez le fichier d'exemple et configurez vos clés API :

```bash
cp .env.exemple .env
```

Éditez `.env` avec vos valeurs :

```env
# MongoDB
MONGO_URI="mongodb+srv://..."
MONGO_DB_NAME="marketpulse"

# Qdrant Cloud
QDRANT_URL="https://ton-cluster.qdrant.tech"
QDRANT_API_KEY="ta_cle_qdrant"

# Cohere
COHERE_API_KEY="ta_cle_cohere"

# Groq
GROQ_API_KEY="ta_cle_groq"
```

## 🚀 Utilisation

### Démarrer l'API

```bash
# Avec UV
uv run uvicorn src.api.main:app --reload

# Ou directement
python -m uvicorn src.api.main:app --reload
```

L'API sera accessible sur `http://localhost:8000`

### Documentation API

Une fois l'API démarrée, accédez à la documentation interactive :
- **Swagger UI** : http://localhost:8000/docs
- **ReDoc** : http://localhost:8000/redoc

### Ingestion des données

#### Collecte automatique (via GitHub Actions)

Le pipeline d'ingestion s'exécute automatiquement toutes les 6 heures via GitHub Actions.

#### Collecte manuelle

```bash
# Collecter les nouveaux articles
uv run python -m src.ingestion.collector

# Vectoriser et indexer
uv run python -m src.ingestion.vectorizer
```

## 🧪 Tests

```bash
# Tests unitaires
uv run pytest tests/unit/

# Tests d'intégration
uv run pytest tests/integration/

# Avec couverture
uv run pytest --cov=src --cov-report=html
```

## 🏗️ Architecture

### Stack Technique

| Composant | Technologie | Version |
|-----------|-------------|---------|
| **Framework Web** | FastAPI | >=0.135.3 |
| **Orchestration RAG** | LlamaIndex | >=0.14.16 |
| **LLM** | Groq (Llama-3) | via API |
| **Embeddings** | Cohere (multilingual-v3.0) | via API |
| **Vector DB** | Qdrant Cloud | >=0.10.0 |
| **Base de données** | MongoDB | >=4.16.0 |
| **Parsing RSS** | feedparser | >=6.0.12 |
| **Extraction texte** | trafilatura | >=2.0.0 |

### Structure du Projet

```
FinSight_RAG/
├── docs/
│   ├── ADR-001-stack-technique.md       # Décisions architecturales
│   └── Architecture.md                  # Documentation technique
│
├── src/
│   ├── config.py                         # Configuration centralisée
│   ├── api/
│   │   ├── main.py                       # Point d'entrée FastAPI
│   │   └── schemas.py                    # Modèles Pydantic
│   ├── rag/
│   │   ├── engine.py                     # Moteur RAG LlamaIndex
│   │   └── prompts.py                    # Templates de prompts
│   ├── ingestion/
│   │   ├── collector.py                  # Collecte des articles
│   │   ├── vectorizer.py                 # Vectorisation et indexation
│   │   └── source.py                     # Sources RSS
│   └── utils/
│       ├── db_client.py                  # Client MongoDB
│       ├── date_parser.py                # Parsing des dates
│       └── logger.py                     # Logger rotatif
│
├── tests/
│   ├── unit/                             # Tests unitaires
│   └── integration/                      # Tests d'intégration
│
├── .github/workflows/
│   └── ingestion.yml                     # Pipeline CI/CD
│
├── logs/                                 # Logs applicatifs
├── Dockerfile                            # Image de déploiement
├── pyproject.toml                        # Configuration projet
├── uv.lock                               # Lock file UV
└── README.md
```

### Flux de Données

1. **Collecte** : Récupération des articles via RSS (feedparser + trafilatura)
2. **Stockage** : Sauvegarde brute dans MongoDB
3. **Vectorisation** : Génération d'embeddings via Cohere API
4. **Indexation** : Stockage dans Qdrant Cloud
5. **Requête** : Recherche vectorielle + génération via Groq

## 🔧 Développement

### Scripts disponibles

```bash
# Démarrer l'API en mode développement
uv run uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# Lancer les tests
uv run pytest

# Formater le code (si black configuré)
uv run black src/

# Vérifier le typage (si mypy configuré)
uv run mypy src/
```

### Variables d'environnement

Voir `.env.exemple` pour la liste complète des variables requises.

## 📊 Monitoring

- **Logs** : Fichiers rotatifs dans `logs/app.log`
- **Tracing** : Langfuse/Arize Phoenix (à configurer)
- **Métriques** : Healthchecks API (`/health`)

## 🤝 Contribution

1. Fork le projet
2. Créez une branche feature (`git checkout -b feature/AmazingFeature`)
3. Committez vos changements (`git commit -m 'Add some AmazingFeature'`)
4. Pushez vers la branche (`git push origin feature/AmazingFeature`)
5. Ouvrez une Pull Request

## 📝 License

Ce projet est sous licence MIT - voir le fichier [LICENSE](LICENSE) pour plus de détails.

## 🙏 Remerciements

- [LlamaIndex](https://www.llamaindex.ai/) pour l'orchestration RAG
- [Qdrant](https://qdrant.tech/) pour la base de données vectorielle
- [Cohere](https://cohere.com/) pour les embeddings
- [Groq](https://groq.com/) pour l'inférence LLM ultra-rapide