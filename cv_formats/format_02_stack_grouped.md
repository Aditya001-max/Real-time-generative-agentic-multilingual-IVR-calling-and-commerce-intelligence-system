# Format 02 — Stack-Grouped (Big Tech / Structured JDs)

**Style:** Bullets grouped by capability domain — Agentic AI, RAG, ML, Voice, Infra, MLOps. Reads well when the JD lists competencies as separate boxes.

---

### Real-Time Generative Agentic Multilingual IVR & Commerce Intelligence Platform
*Self Project · National Finalist, Gappy AI · 2025–2026*

Production-grade agentic voice + WhatsApp AI platform for Indian e-commerce, spanning 9 Indian languages with dynamic code-mixed conversation.

**Agentic Orchestration**
- Built a **LangGraph** agent with 15+ enterprise tools (CRM, OMS, Product Search, Order Tracking, RTO, Knowledge Base, Ticketing, Customer History, Recommender, Courier, WhatsApp, Payments, Escalation, Notifications, Analytics), long-term memory and policy-controlled execution.

**LLM Serving & Fine-Tuning**
- Served **Llama 3.3 70B via vLLM** (continuous batching, paged attention) with **LoRA / QLoRA fine-tuning** and instruction tuning for Indian e-commerce.

**Retrieval-Augmented Generation**
- Engineered hybrid RAG with **BGE-M3 multilingual embeddings + Qdrant (dense) + OpenSearch (BM25)** over product catalogs, FAQs, return policies and shipping SOPs.

**Real-Time Voice**
- Streaming pipeline: **Deepgram STT + Coqui XTTS**, barge-in, interruption handling, voice continuity, mid-call language switching across 9 Indian languages.

**Classical ML**
- **XGBoost / LightGBM** models for intent, sentiment, churn, RTO, fraud, CLV, segmentation, retry optimisation and personalised product ranking.

**Backend & Integrations**
- **Python 3.12 / FastAPI + PostgreSQL + Redis + Kafka**; integrated Twilio, WhatsApp Cloud, Shopify, Chatwoot and courier APIs with HMAC-verified webhooks.

**MLOps & Observability**
- **MLflow** (registry), **Langfuse** (LLM traces), **Evidently AI** (drift), **Prometheus + Grafana** — deployed on **Docker + Kubernetes** with horizontal autoscaling.
