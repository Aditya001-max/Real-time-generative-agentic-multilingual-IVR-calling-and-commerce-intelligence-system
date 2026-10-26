# Format 01 — Impact-Led (Senior GenAI Engineer)

**Style:** Every bullet leads with a measurable or business outcome, then the technical mechanism. Best when applying to senior GenAI Engineer roles where hiring managers screen for *impact per system*, not tool lists.

---

### Real-Time Generative Agentic Multilingual IVR & Commerce Intelligence Platform
*Self Project · National Finalist, Gappy AI · 2025–2026*

Autonomous voice + WhatsApp AI agent for Indian e-commerce — handling COD verification, RTO recovery, order support, recommendations and human escalation in 9 Indian languages with real-time code-mixed conversation.

- **Replaced ₹15–30/call human tele-calling with a ~₹0.30–1/call agentic AI**, targeting 20–40% RTO reduction — orchestrated via **LangGraph** with 15+ tools (CRM, OMS, Courier, WhatsApp, Ticketing, RAG, Recommendations).
- **Cut LLM hallucinations on domain queries** through a **BGE-M3 + Qdrant + OpenSearch hybrid RAG** grounding responses in product catalogs, return policies and business SOPs.
- **Delivered sub-second turn latency** on real-time voice via **Deepgram streaming STT + Coqui XTTS** with barge-in, interruption handling and mid-call language switching across 9 languages.
- **Specialised Llama 3.3 70B for Indian e-commerce** using **LoRA / QLoRA fine-tuning + instruction tuning**, served on **vLLM** with continuous batching for high throughput.
- **Automated retry, RTO and fraud decisions** with **XGBoost / LightGBM** models (intent, sentiment, churn, CLV, segmentation, retry-time optimisation, product ranking) trained on transactional + conversational signals.
- **Shipped production infra on Kubernetes** — FastAPI + PostgreSQL + Redis + Kafka; integrated Twilio, WhatsApp Cloud, Shopify, Chatwoot and courier APIs with HMAC-verified webhooks.
- **Selected as National Finalist at Gappy AI** among competing teams nationwide for production-readiness and technical depth.

**Stack:** LangGraph · vLLM · Llama 3.3 70B · LoRA/QLoRA · BGE-M3 · Qdrant · OpenSearch · Deepgram · Coqui XTTS · XGBoost · LightGBM · FastAPI · PostgreSQL · Redis · Kafka · Kubernetes · MLflow · Langfuse
