# Format 04 — Narrative Hybrid (Startups / Founder-Facing)

**Style:** Short story paragraph + supporting bullets. Reads as if you're describing the system to a founder over coffee. Best for startup GenAI roles where taste and judgement matter more than checklist coverage.

---

### Real-Time Generative Agentic Multilingual IVR & Commerce Intelligence Platform
*Self Project · National Finalist, Gappy AI · 2025–2026*

Indian D2C brands lose 20–40% of COD margin to Return-to-Origin. Tele-callers cost ₹15–30/call and don't scale. I built an **autonomous multilingual AI employee** that takes over the entire outbound + inbound conversation — voice and WhatsApp — across **9 Indian languages** with real-time code-mixed conversation, at **~₹0.30–1/call**.

Under the hood, a **LangGraph** agent reasons over 15+ enterprise tools (CRM, OMS, Courier, WhatsApp, Ticketing, Recommender, RAG) with long-term customer memory and policy guards. Conversation runs on **Llama 3.3 70B via vLLM**, domain-tuned with **LoRA / QLoRA**, grounded by a hybrid **BGE-M3 + Qdrant + OpenSearch** RAG over product catalogs, return policies and business SOPs. Voice is **Deepgram STT + Coqui XTTS**, streaming, with barge-in and mid-call language switching.

- **XGBoost / LightGBM** models drive intent, sentiment, churn, RTO, fraud, CLV, retry timing and product ranking.
- **FastAPI + PostgreSQL + Redis + Kafka** on **Kubernetes**, integrated with **Twilio, WhatsApp Cloud, Shopify, Chatwoot** and courier APIs.
- **MLflow, Langfuse, Evidently, Prometheus, Grafana** for continuous evaluation, LLM observability and drift detection.
- **National Finalist, Gappy AI** — recognised for production-readiness and technical depth.
