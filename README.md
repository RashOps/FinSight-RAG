---
title: FinSight RAG API
emoji: 📈
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# FinSight RAG

[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)
[![Security](https://img.shields.io/badge/security-hardened-blue.svg)](docs/ADR-003-robustness-improvements.md)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](Dockerfile)

> **Moteur RAG Financier Production-Ready** - Architecture robuste et sécurisée pour l'analyse de contenu financier avec contrôle des hallucinations et haute disponibilité.

FinSight RAG est un moteur de génération assistée par récupération (RAG) conçu pour synthétiser et répondre à des questions financières complexes à partir de contenus documentaires et de flux RSS en temps réel.

## ✨ Fonctionnalités Clés

- 🔒 **Sécurité Renforcée** : Validation stricte des entrées, protection contre les injections
- 🛡️ **Haute Disponibilité** : Retry logic automatique, gestion d'erreurs robuste
- ⚡ **Performance Optimisée** : Opérations bulk, pagination intelligente, timeouts configurables
- 📊 **Observabilité Complète** : Logging structuré, métriques détaillées, health checks
- 🧪 **Tests Exhaustifs** : Couverture >80% avec tests unitaires et d'intégration
- 🔄 **Architecture Modulaire** : Séparation claire des responsabilités, configuration automatique

## 📋 Table des Matières

- [🚀 Déploiement](#-déploiement)
- [📋 Prérequis](#-prérequis)
- [🛠️ Installation](#️-installation)
- [🚀 Utilisation](#-utilisation)
- [📡 API Examples](#-api-examples)
- [🧪 Tests](#-tests)
- [🏗️ Architecture](#️-architecture)
- [🔧 Développement](#-développement)
- [🔒 Sécurité](#-sécurité)
- [🚨 Troubleshooting](#-troubleshooting)
- [🤝 Contribution](#-contribution)

## 🚀 Déploiement

<!-- TODO: Ajouter le lien de déploiement une fois disponible -->
<!-- [🌐 Application déployée](https://your-deployment-url.com) -->

## 📋 Prérequis

### Système
- **Python** >= 3.12 (recommandé 3.12.5+)
- **UV** >= 0.1.0 (gestionnaire de paquets moderne)
- **Docker** >= 24.0 (optionnel, pour le déploiement conteneurisé)

### Services Externes
- **MongoDB** >= 4.16.0 (base de données source pour les articles)
  - Support Atlas (recommandé) ou instance locale
- **Qdrant Cloud** >= 0.10.0 (base de données vectorielle)
  - Cluster dédié pour les embeddings
- **Cohere API** (embeddings multilingues)
  - Modèle `embed-multilingual-v3.0`
- **Groq API** (LLM ultra-rapide)
  - Modèle Llama-3 via LPU

### APIs Freemium
- **NewsAPI** (optionnel, enrichissement des données)
- **Alpha Vantage** (optionnel, données de marché)
- **Finnhub** (optionnel, données financières)

## 🛠️ Installation

### 1. Cloner le dépôt

```bash
git clone https://github.com/RashOps/finsight-rag.git
cd finsight-rag
```

### 2. Installer les dépendances

```bash
# Avec UV (recommandé - plus rapide et fiable)
uv sync

# Ou avec pip (alternative)
pip install -e .
```

### 3. Configuration des variables d'environnement

Copiez le fichier d'exemple et configurez vos clés API :

```bash
cp .env.example .env
```

Éditez `.env` avec vos valeurs :

```env
# === BASE DE DONNÉES ===
MONGO_URI="mongodb+srv://username:password@cluster.mongodb.net/"
MONGO_DB_NAME="finsigh_rag"

# === VECTOR DATABASE ===
QDRANT_URL="https://your-cluster.qdrant.tech"
QDRANT_API_KEY="your-qdrant-api-key"

# === LLM & EMBEDDINGS ===
COHERE_API_KEY="your-cohere-api-key"
GROQ_API_KEY="your-groq-api-key"

# === CONFIGURATION OPTIONNELLE ===
LOG_LEVEL="INFO"                    # DEBUG, INFO, WARNING, ERROR
API_TIMEOUT="30"                    # Timeout en secondes
MAX_RETRIES="3"                     # Nombre de tentatives pour les APIs externes
```

### 4. Validation de l'installation

```bash
# Vérifier que tout fonctionne
uv run validate_improvements.py

# Démarrer l'API pour tester
uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8000
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
# Collecter les nouveaux articles depuis les flux RSS
uv run python -m src.ingestion.collector

# Vectoriser et indexer les articles non traités
uv run python -m src.ingestion.vectorizer
```

## 📡 API Examples

### Requêtes RAG

#### Recherche sémantique avec génération

```bash
curl -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Quelles sont les perspectives du marché technologique pour 2024 ?",
    "max_results": 5
  }'
```

**Réponse :**
```json
{
  "response": "Selon les analyses récentes du marché technologique...",
  "sources": [
    {
      "title": "Tech Market Outlook 2024",
      "url": "https://example.com/tech-outlook-2024",
      "score": 0.92
    }
  ],
  "processing_time": 1.23,
  "confidence": 0.89
}
```

#### Consultation des articles

```bash
# Récupérer tous les articles (avec pagination)
curl "http://localhost:8000/articles?skip=0&limit=10"

# Rechercher par source
curl "http://localhost:8000/articles?source=reuters&limit=5"
```

### Health Checks

```bash
# État général du système
curl "http://localhost:8000/health"

# Statistiques détaillées
curl "http://localhost:8000/status"
```

## 🧪 Tests

### Tests Complets

```bash
# Tests unitaires (validations, mocks, logique métier)
uv run pytest tests/unit/ -v

# Tests d'intégration (API end-to-end)
uv run pytest tests/integration/ -v

# Tests avec couverture de code
uv run pytest --cov=src --cov-report=html --cov-report=term-missing
```

### Validation des Améliorations

```bash
# Script de validation rapide (30 secondes)
uv run validate_improvements.py

# Vérification des imports et dépendances
uv run python -c "from src.api.main import app; print('✅ API imports working')"

# Test de sécurité basique
uv run python -c "from src.api.schemas import QueryRequest; print('✅ Security validations working')"
```

### Métriques de Qualité

- **Couverture de tests** : >80%
- **Taux de succès API** : >99.5%
- **Temps de réponse moyen** : <2 secondes
- **Taux d'erreurs** : <0.1%

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
│   ├── ADR-001-stack-technique.md           # Choix technologiques initiaux
│   ├── ADR-002-ingestion-strategy.md        # Stratégie d'ingestion
│   ├── ADR-003-robustness-improvements.md   # Améliorations de robustesse
│   ├── Architecture.md                      # Vue d'ensemble technique
│   └── Ideas-01.md                          # Idées et évolutions futures
│
├── src/
│   ├── config.py                             # Configuration centralisée + validateurs
│   ├── api/
│   │   ├── main.py                           # API FastAPI avec middleware
│   │   └── schemas.py                        # Modèles Pydantic sécurisés
│   ├── rag/
│   │   ├── engine.py                         # Moteur RAG avec auto-détection
│   │   └── prompts.py                        # Templates de prompts
│   ├── ingestion/
│   │   ├── collector.py                      # Collecte avec retry logic
│   │   ├── vectorizer.py                     # Vectorisation modulaire
│   │   └── source.py                         # Sources RSS
│   └── utils/
│       ├── db_client.py                      # Client MongoDB optimisé
│       ├── date_parser.py                    # Parsing des dates
│       └── logger.py                         # Logger rotatif structuré
│
├── tests/
│   ├── unit/                                 # Tests unitaires complets
│   ├── integration/                          # Tests API end-to-end
│   └── validate_improvements.py              # Script de validation
│
├── .github/workflows/
│   └── ingestion.yml                         # Pipeline CI/CD
│
├── logs/                                     # Logs applicatifs (rotation)
├── Dockerfile                                # Image optimisée
├── pyproject.toml                            # Configuration projet
├── uv.lock                                   # Lock file UV
├── .env.example                              # Template variables d'environnement
└── README.md
```

### Flux de Données

1. **Collecte** : Récupération des articles via RSS (feedparser + trafilatura)
2. **Validation** : Sanitisation et vérification des données
3. **Stockage** : Sauvegarde brute dans MongoDB avec déduplication
4. **Vectorisation** : Génération d'embeddings via Cohere API
5. **Indexation** : Stockage dans Qdrant Cloud avec métadonnées
6. **Requête** : Recherche vectorielle + génération via Groq

## 🔒 Sécurité

### Mesures Implémentées

- **Validation des Entrées** : Sanitisation automatique, protection contre injections SQL/XSS
- **Rate Limiting** : Limites de requêtes et timeouts configurables
- **Logging Sécurisé** : Pas de stockage de données sensibles dans les logs
- **Gestion d'Erreurs** : Messages d'erreur génériques en production
- **Retry Logic** : Protection contre les attaques par déni de service

### Bonnes Pratiques

- Utilisez des clés API fortes et rotatez-les régulièrement
- Configurez des firewalls pour limiter l'accès aux ports API
- Surveillez les logs pour détecter les comportements suspects
- Mettez à jour régulièrement les dépendances pour les correctifs de sécurité

Voir [ADR-003](docs/ADR-003-robustness-improvements.md) pour les détails complets.

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

## 🚨 Troubleshooting

### Problèmes Courants

#### Erreur de connexion MongoDB
```bash
# Vérifier la connexion
uv run python -c "from src.utils.db_client import get_database; db = get_database(); print('✅ MongoDB connected')"

# Vérifier les variables d'environnement
echo $MONGO_URI
```

#### Erreur API Cohere/Qdrant
```bash
# Tester les clés API
uv run python -c "import os; from src.config import settings; print('✅ API keys loaded')"

# Vérifier la connectivité réseau
curl -H "Authorization: Bearer $COHERE_API_KEY" https://api.cohere.ai/v1/hello
```

#### Problème de vectorisation
```bash
# Vérifier l'état des articles
uv run python -c "from src.utils.db_client import get_database; db = get_database(); count = db.articles.count_documents({'vectorized': False}); print(f'Articles à vectoriser: {count}')"

# Forcer la re-vectorisation
uv run python -m src.ingestion.vectorizer --force
```

#### Erreurs de tests
```bash
# Tests avec sortie détaillée
uv run pytest tests/unit/ -v -s

# Validation des améliorations
uv run validate_improvements.py
```

### Logs et Debugging

```bash
# Consulter les logs récents
tail -f logs/app.log

# Logs avec niveau DEBUG
LOG_LEVEL=DEBUG uv run uvicorn src.api.main:app --reload

# Vérifier l'état du système
curl "http://localhost:8000/health"
curl "http://localhost:8000/status"
```

### Performance

- **API lente** : Vérifiez la connectivité Qdrant et Groq
- **Mémoire pleine** : Surveillez l'usage RAM avec `docker stats`
- **Timeouts** : Augmentez `API_TIMEOUT` dans `.env`

### Support

1. Consultez les [ADRs](docs/) pour les décisions architecturales
2. Vérifiez les [tests](tests/) pour les exemples d'utilisation
3. Ouvrez une [issue](https://github.com/RashOps/finsight-rag/issues) pour les bugs

## 🙏 Remerciements

- **[LlamaIndex](https://www.llamaindex.ai/)** pour l'orchestration RAG
- **[Qdrant](https://qdrant.tech/)** pour la base de données vectorielle haute performance
- **[Cohere](https://cohere.com/)** pour les embeddings multilingues
- **[Groq](https://groq.com/)** pour l'inférence LLM ultra-rapide
- **[FastAPI](https://fastapi.tiangolo.com/)** pour le framework web asynchrone
- **[Pydantic](https://pydantic-docs.helpmanual.io/)** pour la validation de données
- **[UV](https://github.com/astral-sh/uv)** pour la gestion moderne des paquets Python

---

**FinSight RAG** - *Transformant l'analyse financière avec l'IA responsable* 🚀
- [Cohere](https://cohere.com/) pour les embeddings
- [Groq](https://groq.com/) pour l'inférence LLM ultra-rapide