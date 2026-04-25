# Utilisation d'une image Python légère et stable
FROM python:3.12-slim

# Arguments de build
ARG PYTHON_VERSION=3.12

# Labels pour les métadonnées
LABEL maintainer="FinSight RAG Team" \
      description="FinSight RAG - Financial RAG system with production-ready robustness" \
      version="1.0.0" \
      python.version="${PYTHON_VERSION}" \
      org.opencontainers.image.source="https://github.com/RashOps/finsight-rag"

# Installation de uv (méthode binaire rapide)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Définition des variables d'environnement Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Création d'un utilisateur non-root pour la sécurité
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash appuser

# Dependances nécessaires
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Création du répertoire de travail
WORKDIR /app

# Création du dossier logs avec les bonnes permissions
RUN mkdir -p logs && \
    chown -R appuser:appuser /app

# Changement vers l'utilisateur non-root AVANT l'installation des dépendances
USER appuser

# On copie d'abord uniquement les fichiers de dépendances pour optimiser le cache Docker
COPY --chown=appuser:appuser pyproject.toml uv.lock ./

# Installation des dépendances (sans les libs de dev et en utilisant le lockfile)
# On pré-compile le bytecode pour de meilleures performances
RUN uv sync --frozen --no-dev --compile-bytecode

# Copie du code source avec les bonnes permissions
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser docs/ ./docs/

# Exposition du port utilisé par FastAPI
EXPOSE 8000

# Volume pour les logs persistants
VOLUME ["/app/logs"]

# Healthcheck pour vérifier que l'API répond
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Commande par défaut : Lancer l'API
# On utilise "uv run" pour s'assurer que le virtualenv est correctement utilisé
CMD ["uv", "run", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]