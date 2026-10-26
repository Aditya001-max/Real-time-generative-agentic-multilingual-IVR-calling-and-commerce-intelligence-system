# Format 06 — Research-Flavoured (AI Research Engineer)

**Style:** Emphasises modelling choices, fine-tuning methodology and evaluation. Downplays integrations and infra. Best for AI Research Engineer or Applied Scientist JDs.

---

### Real-Time Generative Agentic Multilingual IVR & Commerce Intelligence Platform
*Self Project · National Finalist, Gappy AI · 2025–2026*

Agentic multilingual voice platform for Indian e-commerce — used as a testbed for grounded LLM reasoning, domain adaptation and multi-lingual retrieval.

- **Fine-tuned Llama 3.3 70B** with **LoRA / QLoRA** and domain-specific instruction tuning on Indian e-commerce dialogues; served via **vLLM** with continuous batching and paged attention.
- **Designed a hybrid multilingual retriever** combining **BGE-M3** dense embeddings (Qdrant) with **BM25 sparse retrieval** (OpenSearch), tuned for code-mixed Hinglish + 9 Indian languages over product catalogs, FAQs and policy documents.
- **Built a LangGraph agent** with 15+ tools, long-term customer memory and policy-controlled execution — studied trade-offs between tool-selection routing, ReAct-style reasoning and constrained decoding for reliability.
- **Instrumented LLM observability with Langfuse**, capturing per-turn traces, tool selection, grounding sources and latency — enabling systematic prompt + retrieval evaluation.
- **Trained classical ML baselines** (XGBoost / LightGBM) for intent, sentiment, churn, RTO, fraud, CLV and product ranking, benchmarked against LLM-only baselines for cost / latency trade-offs.
- **Real-time voice**: Deepgram streaming STT + Coqui XTTS with barge-in, interruption handling and mid-call language switching across 9 Indian languages.

**Stack:** Llama 3.3 70B · vLLM · LoRA/QLoRA · LangGraph · BGE-M3 · Qdrant · OpenSearch · Langfuse · MLflow · Evidently · XGBoost · LightGBM · Deepgram · Coqui XTTS
