# FinSight RAG

FinSight RAG est un moteur de génération assistée par récupération (RAG) conçu pour synthétiser et répondre à des questions financières à partir de contenus documentaires et de flux de données.

Ce projet a pour objectif de proposer une architecture légère et résiliente, pensée pour fonctionner dans des environnements contraints (Free Tier, 1 vCPU, 512 MB RAM), tout en conservant des garanties de qualité de réponse et de contrôle des hallucinations.

Il repose sur une séparation claire des responsabilités :
- ingestion et indexation des données financières,
- stockage vectoriel déporté pour les embeddings,
- orchestration de la recherche et de la génération via LlamaIndex,
- exposition d'une API FastAPI pour les requêtes en temps réel.

Le dépôt est destiné à servir de base à un service RAG financier capable de répondre en langage naturel à des demandes analytiques et de veille, tout en gardant une infrastructure simple et maintenable.