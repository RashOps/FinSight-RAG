# ADR 001 : Architecture and Technical Stack for Financial RAG Engine

## 1. Status
**Accepted** (2026-04-10)

## 2. Context
The objective is to build a Retrieval-Augmented Generation (RAG) engine capable of synthesizing and answering queries based on real-time financial news. The system must operate under strict infrastructure constraints (Free Tier hosting: 1 vCPU, 512 MB RAM) while delivering production-grade accuracy, zero hallucinations, and sub-second latency.

## 3. Decisions

### 3.1. Orchestration Framework: LlamaIndex
* **Why:** LlamaIndex is purpose-built for data ingestion, indexing, and retrieval. Its native chunking algorithms and hierarchical indexing capabilities are mathematically superior for document-heavy contexts compared to LangChain.
* **Trade-off:** Slightly less flexible than LangChain for building multi-tool autonomous agents, but guarantees higher retrieval precision for financial text.

### 3.2. Vector Database: Qdrant Cloud
* **Why:** Open-source, written in Rust (high throughput, low latency). The Cloud Free Tier allows for remote storage of embeddings, strictly avoiding local RAM consumption on the hosting environment.
* **Trade-off:** Network latency (API calls) is introduced compared to an in-memory local vector store (like FAISS), but prevents `OOMKill` crashes on small containers.

### 3.3. Embeddings Model: Cohere (`embed-multilingual-v3.0`)
* **Why:** State-of-the-art multilingual embedding model. Cohere provides a generous developer tier, completely offloading the heavy matrix multiplications from our server.

### 3.4. LLM Inference: Groq (Llama-3)
* **Why:** Groq utilizes LPU (Language Processing Units) enabling inference speeds exceeding 800 tokens/second. The API is free and OpenAI-compatible, ensuring immediate response times for the end user.

### 3.5. Infrastructure & CI/CD: Docker + Koyeb/Render + GitHub Actions
* **Why:** FastAPI backend wrapped in a lightweight `python:3.12-slim` Docker image. GitHub Actions will automate the test suite (`pytest`) and deployment.
* **Trade-off:** The backend acts strictly as an API Gateway (I/O Bound). No heavy ML computations will ever run locally.

### 3.6 Monitoring : Langfuse/Arize Phoenix
* **Why:** To determine If the mistake come from the document (Qdrant) or from the LLMs hallucination.

## 4. Consequences
* **Positive:** The architecture is highly scalable, incredibly fast, and costs $0/month. The decoupled design allows swapping LLMs or Vector DBs independently.
* **Negative:** High reliance on external APIs. Strict management of API keys and robust network exception handling (`httpx.TimeoutException`) will be required.