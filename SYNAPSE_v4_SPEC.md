# SYNAPSE v4.0 — System Specification

> **Version:** 4.0.0 · **Author:** Sarvesh Bhattacharyya · **Updated:** May 2026

SYNAPSE (Systematic, Yet Natural, Automated, Provenance-aware Schema Engine) is a live AI knowledge graph with a 7-node LangGraph reasoning engine layered above it. It tracks entities across the AI ecosystem via 9 daily API sources, stores them in Neo4j and Qdrant, and answers complex analytical questions using a budget-aware multi-agent pipeline grounded in the graph.

---

## 1. Architecture

### 1.1 v3.0 Foundation — Ingestion, Storage, API

```
9 API Sources (arXiv, HF, GitHub, Semantic Scholar, PapersWithCode, DAIR.AI)
    │
    ▼  parallel fetch + circuit breaker + exponential backoff
SourceFactory → GenericSourceFetcher → SourceDocument[]
    │
    ▼  fast_path_transform + extract_relationships (83 topic mappings)
GraphNode[] + GraphEdge[]  (batched MERGE, 200/batch)
    │
    ▼  embed (gte-small, 384-dim) + semantic similarity (cosine ≥ 0.85)
Neo4j Aura Free (200K nodes, 400K edges) + Qdrant Cloud (1M vectors)
    │
    ▼  FastAPI :8082  ───  React 19 SPA :5173
NL-to-Cypher, search, similarity, diff, leaderboard, ecosystem graph
```

### 1.2 v4.0 Reasoning Engine — 7-Node LangGraph Pipeline

```
User Query
    │
    ▼
┌─ Node 1: Entry ───────────────────────────────────────┐
│  Budget Oracle check, session init                     │
│  6 Groq models tracked (RPM/RPD/TPM)                  │
└──────────────────────┬─────────────────────────────────┘
                       ▼
┌─ Node 2: Decomposition ────────────────────────────────┐
│  GPT-OSS 20B (reasoning=low)                          │
│  Query → sub-questions + search plan (JSON)           │
└──────────────────────┬─────────────────────────────────┘
                       ▼
┌─ Node 3: Retrieval ────────────────────────────────────┐
│  4-tier hybrid: Neo4j KG → cache → vector+BM25 →      │
│  session index. LlamaIndex RouterQueryEngine.         │
│  If confidence < 0.65 → Node 4 fires.                │
└──────────────────────┬─────────────────────────────────┘
                       ▼
┌─ Node 4: Web Research (conditional) ──────────────────┐
│  DuckDuckGo + Tavily + Crawl4AI (ZenRows fallback)    │
│  Content → session-scoped LlamaIndex                  │
└──────────────────────┬─────────────────────────────────┘
                       ▼
┌─ Node 5: Analysis Crew ───────────────────────────────┐
│  Extractor (8B, plain) → Analyzer (Scout, plain)     │
│  → Contradiction Detector (Scout, CrewAI)            │
└──────────────────────┬─────────────────────────────────┘
                       ▼
┌─ Node 6: Synthesis ───────────────────────────────────┐
│  Llama 3.3 70B (once/session)                        │
│  → structured Markdown (Summary, Key Findings,       │
│     Evidence Table, Contradictions, Gaps, Sources)    │
└──────────────────────┬─────────────────────────────────┘
                       ▼
┌─ Node 7: Critic ──────────────────────────────────────┐
│  GPT-OSS 20B (reasoning=medium)                      │
│  grounding · completeness · logic                    │
│  PASS → Output | FAIL → retry N5 (max 2)             │
└──────────────────────┬─────────────────────────────────┘
                       ▼
┌─ Output Node ─────────────────────────────────────────┐
│  Template assembly (zero LLM) + RAGAS evaluation      │
│  Markdown rendered in React browser.                  │
└───────────────────────────────────────────────────────┘
```

---

## 2. Model Assignment Matrix

### Groq Free Tier (6 models, verified May 2026)

| Model | RPM | TPM | RPD | Role |
|-------|-----|-----|-----|------|
| Llama 3.1 8B | 30 | 6,000 | 14,400 | Extractor, classification, routing |
| Llama 4 Scout | 30 | 30,000 | 1,000 | Analyzer, Contradiction Detector |
| Qwen3-32B | 60 | 6,000 | 1,000 | Fallback (secondary) |
| Llama 3.3 70B | 30 | 6,000 | 1,000 | Synthesis (once/session) |
| GPT-OSS 20B | 30 | 8,000 | 1,000 | Decomposition, Critic |
| GPT-OSS 120B | 30 | 8,000 | 1,000 | Critic escalation (double-fail only) |

**Prompt caching:** GPT-OSS models cache static prefixes (zero TPM for system prompts). Llama models do not.

**Local (zero API cost):** gte-small embeddings (384-dim) + spaCy NER + BM25 + OpenCV + ONNX Runtime.

---

## 3. Groq Rate Limits & Key Rotation

- `api/groq_manager.py` — Multi-key rotation manager (comma-separated `GROQ_API_KEYS`)
- Round-robin with health checks (ACTIVE → DEPLETED → ERROR → COOLDOWN)
- 5 errors → 10-minute cooldown
- `execute_with_rotation()` auto-retries across keys (max 2× keys)

---

## 4. Directory Structure

```
synapse/
├── api/                        # FastAPI server (main entry point: uvicorn api.main:app)
│   ├── main.py                 # App entry — v4.0.0, CORS, v1 + v4 routers
│   ├── middleware.py            # Rate limit 120/min, security headers
│   ├── groq_manager.py         # Multi-key rotation + model selection
│   ├── query.py                # Safe Cypher templates + validation
│   └── v1/
│       ├── router.py           # v3.0 endpoints (health, search, similar, etc.)
│       ├── groq_status.py      # Groq key/model monitoring
│       └── reasoning.py        # v4.0: /reason, /ingest, /budget, /eval, /webhook
│
├── budget/                     # Token Budget Controller
│   ├── oracle.py               # Budget Oracle — async singleton, DynamoDB restore
│   ├── register.py             # Per-model RPM (60s window), RPD, TPM
│   ├── scheduler.py            # Leaky Bucket Scheduler (per-model semaphores)
│   ├── fallback_chains.yaml    # Per-task fallback model sequences (YAML)
│   ├── prompt_caching.py       # GPT-OSS models get 75% token cost reduction
│   ├── dynamodb.py             # Budget + job persistence (DynamoDB)
│   └── sqs_queue.py            # SQS job queue (decouples API from EC2)
│
├── providers/                  # InferenceProvider Protocol
│   ├── protocol.py             # InferenceProvider, AssembledPrompt, InferenceResult
│   ├── groq_provider.py        # Wraps GroqKeyManager (one instance per model)
│   └── local_provider.py       # spaCy/BM25/rule-based fallback
│
├── prompt/                     # Prompt Assembly Layer (mandatory pre-inference)
│   ├── assembler.py            # 5-layer builder + budget trimming + tiktoken
│   ├── roles/                  # Static system prompts (cached, zero TPM on GPT-OSS)
│   │   ├── extractor.txt       #   Extractor agent — factual claims, entities
│   │   ├── analyzer.txt        #   Analyzer agent — claim-evidence map
│   │   ├── contradiction_detector.txt
│   │   ├── synthesizer.txt     #   Synthesis — structured Markdown output contract
│   │   ├── critic.txt          #   Critic — grounding, completeness, logic
│   │   └── decomposition.txt   #   Decomposition — sub-questions + search plan
│   └── templates/              # (Pandoc template removed — Markdown output only)
│
├── reasoning/                  # 7-node LangGraph reasoning pipeline
│   ├── graph/
│   │   ├── builder.py          # Loads YAML topology, builds StateGraph
│   │   ├── state.py            # ReasoningState dataclass
│   │   ├── checkpoint.py       # PostgreSQL checkpoint (entry/synthesis/output)
│   │   └── definitions/default.yaml  # Graph topology (nodes, edges, budget gates)
│   ├── nodes/
│   │   ├── entry.py            # Budget check, session init
│   │   ├── decomposition.py    # GPT-OSS 20B → sub-questions + search plan
│   │   ├── retrieval.py        # 4-tier hybrid retrieval
│   │   ├── analysis_crew.py    # Extractor + Analyzer + ContradictionDetector
│   │   ├── contradiction_detector.py  # CrewAI agent (falls back to plain node)
│   │   ├── synthesis.py        # Llama 3.3 70B → structured Markdown
│   │   ├── critic.py           # GPT-OSS 20B → pass/fail + retry loop
│   │   └── output.py           # Template assembly + RAGAS evaluation
│   └── subagents/
│       ├── manager.py          # Budget-sliced subgraph spawner
│       └── web_research.py     # Crawl4AI + DuckDuckGo + Tavily + ZenRows
│
├── retrieval/                  # LlamaIndex data layer
│   ├── index_builder.py        # VectorStoreIndex (Qdrant) + BM25 + KGIndex
│   ├── query_engines.py        # query_vector, query_bm25, query_hybrid
│   ├── session_index.py        # Session-scoped in-memory index
│   └── web_research_cache.py   # Cross-session WebResearchResult cache (Neo4j)
│
├── mcp/                        # MCP client layer (stdio transport)
│   ├── client.py               # Memory, Sequential Thinking, Filesystem servers
│   └── tool_registry.py        # LangChain-compatible tool wrappers
│
├── eval/                       # RAGAS monitoring
│   └── ragas_monitor.py        # Faithfulness, relevancy, precision, recall
│
├── embedding/                  # Vector embeddings
│   ├── generator.py            # all-MiniLM-L6-v2 (384-dim)
│   ├── onnx_generator.py       # ONNX Runtime drop-in (2-3x faster)
│   └── qdrant_client.py        # Qdrant singleton client
│
├── nlp/                        # Local NLP (zero API cost)
│   ├── spacy_pipeline.py       # spaCy en_core_web_trf + fastcoref
│   └── opencv_processor.py     # Layout analysis, table extraction
│
├── sync/                       # Background content acquisition
│   ├── background_scraper.py   # 9-source 6-hourly scrape + 5-gate verifier
│   └── reject_log.jsonl        # Audit trail for rejected content
│
├── config/
│   └── thresholds.yaml         # Retrieval, critic, budget thresholds
│
├── ingestion/                  # Data pipeline (v3.0, extended)
│   ├── sources/base.py         # SourceDocument, SourceManifest, SourceFetcher ABC
│   ├── generic_source.py       # Universal JSON/XML/RSS fetcher
│   ├── source_factory.py       # YAML → fetcher factory
│   ├── circuit_breaker.py      # CircuitBreaker (3 fails → 30min OPEN)
│   ├── circuit_breaker_wrapper.py  # Exponential backoff wrapper + decorator
│   ├── embedding_pipeline.py   # Batch embedding → Qdrant + Neo4j
│   ├── semantic_similarity.py  # SEMANTICALLY_SIMILAR edges (cosine ≥ 0.85)
│   ├── checkpoint/postgres.py  # PostgreSQL checkpoint manager
│   ├── neo4j/client.py         # Async Neo4j driver wrapper
│   ├── neo4j/writer.py         # Batched MERGE writer (200/batch)
│   └── pipeline/
│       ├── run.py              # Main orchestrator (4 stages + embedding + webhook)
│       ├── state.py            # PipelineState dataclass
│       ├── extraction.py       # fast_path_transform
│       ├── relationships.py    # 83 topic→technique mappings, edge extraction
│       └── observability.py    # RunTrace → JSONL
│
├── schema/                     # Data models + config
│   ├── config.py               # Settings (Pydantic, @lru_cache)
│   ├── models.py               # GraphNode, GraphEdge, ProvenanceRecord, etc.
│   ├── setup.py                # Neo4j schema initializer
│   └── domain_loader.py        # Domain pack loader (YAML + JSONL)
│
├── domains/ai/                 # AI domain configuration
│   ├── schema.yaml             # 14 node types, 20 relationship types
│   ├── sources.yaml            # 9 data source definitions
│   ├── aliases.jsonl            # 213 technique name aliases
│   ├── eval_gold.jsonl         # 3 golden evaluation queries
│   ├── prompts.py              # LLM prompt templates
│   ├── templates.py            # Safe Cypher query templates
│   └── ranking.py              # compute_rank() weighted formula
│
├── webhook/                    # Push notifications
│   ├── registry.py             # Subscription model + HMAC signing
│   └── dispatcher.py           # Async dispatch with retry (30s→5m→30m)
│
├── export/graph_exporter.py    # JSON-LD / CSV ZIP / GraphML
├── admin/review_queue.py       # PostgreSQL-backed review queue
├── query/nl_to_cypher.py       # NL-to-Cypher translator (Llama 4 Scout)
├── seed/run.py                 # N-day synthetic test data generator
│
├── frontend/                   # React 19 SPA (Vite + TailwindCSS + TanStack Query)
│   └── src/pages/
│       ├── dashboard.tsx       # Animated counters, source ticker
│       ├── search.tsx          # Full-text search with type filters
│       ├── ask.tsx             # NL query interface
│       ├── reason.tsx          # Deep Reasoning — live pipeline stages + RAGAS scores
│       ├── graph.tsx           # Sigma.js WebGL graph explorer
│       ├── ingest.tsx          # Drag-and-drop document upload
│       ├── diff.tsx            # Temporal diff between dates
│       ├── leaderboard.tsx     # Top tools/papers/techniques
│       ├── quality.tsx         # RAGAS eval dashboard + system health
│       ├── budget.tsx          # Per-model token budget bars (10s refresh)
│       ├── export.tsx          # Subgraph export (3 formats)
│       ├── docs.tsx            # API quick reference
│       └── about.tsx           # Architecture + credits
│
├── tests/                      # Python test suite
├── scripts/                    # Developer utilities (16 scripts)
├── .github/workflows/          # CI/CD
│   ├── daily_ingest.yml        # 00:00 UTC — 9 API source ingestion
│   ├── background_scrape.yml   # Every 6h — 9-source curated content scrape
│   ├── weekly_archive.yml      # Sunday 01:00 — pipeline + snapshot
│   └── weekly_eval.yml         # Sunday 02:00 — pytest
│
├── main.py                     # Scaffold entry
├── pyproject.toml              # Dependencies, build config, Python >=3.12
├── .env.example                # All environment variables documented
├── README.md                   # Public documentation
└── SYNAPSE_v4_SPEC.md          # This file
```

---

## 5. v4.0 Pipeline Nodes (Details)

### Node 1: Entry (`reasoning/nodes/entry.py`)
- Reads all model budgets from Budget Oracle
- Estimates query complexity (by length)
- Returns routing plan; if all models exhausted → graceful degradation
- Initializes session UUID

### Node 2: Decomposition (`reasoning/nodes/decomposition.py`)
- GPT-OSS 20B at `reasoning_effort="low"`
- Output JSON: sub_questions (ranked), search_queries (5-7 with types), retrieval_strategy, complexity map, merge_strategy
- JSON validation failure → 8B retry once → fallback to raw query

### Node 3: Retrieval (`reasoning/nodes/retrieval.py`)
- 4-tier: Neo4j KG (zero tokens) → Cross-session cache → Vector/BM25/Qdrant → Session index
- 8B classifier routes index selection (cheap, < 100 tokens)
- Confidence computed from result count, KG hit ratio, score distribution
- Confidence < 0.65 → triggers Node 4 web research

### Node 4: Web Research (`reasoning/subagents/web_research.py`)
- DuckDuckGo: all queries (free, no API key)
- Tavily: top 2-3 by priority (AI-ranked, `TAVILY_API_KEY`)
- Crawl4AI: Playwright-backed JS rendering → clean Markdown
- ZenRows: circuit-breaker fallback on anti-bot failure (`ZENROWS_API_KEY`)
- Results stored in session-scoped LlamaIndex index
- After session: persisted to Neo4j as `WebResearchResult` nodes (7-day TTL)

### Node 5: Analysis Crew (`reasoning/nodes/analysis_crew.py`)
- Extractor: Llama 3.1 8B (plain LangGraph node, zero CrewAI overhead)
- Analyzer: Llama 4 Scout (plain LangGraph node, zero CrewAI overhead)
- Contradiction Detector: CrewAI agent (Agent + Task + Crew) with Scout; falls back to plain node if CrewAI not installed

### Node 6: Synthesis (`reasoning/nodes/synthesis.py`)
- Llama 3.3 70B (once per session, highest quality call)
- Receives structured claim-evidence map, not raw documents
- Output: Markdown with Summary, Key Findings (confidence-annotated), Evidence Table, Contradictions, Knowledge Gaps, Sources

### Node 7: Critic (`reasoning/nodes/critic.py`)
- GPT-OSS 20B at `reasoning_effort="medium"`
- Evaluates: grounding (traceable to source?), completeness (all sub-questions answered?), logic (conclusions follow?)
- PASS → Output. FAIL → retry Analysis (max 2). Double fail → 120B escalation → output best available with `confidence_ceiling` annotation

### Output Node (`reasoning/nodes/output.py`)
- Template assembly (zero LLM)
- Builds source citation list, knowledge gaps list
- Triggers RAGAS evaluation: sends (query, answer, contexts) to Groq 8B LLM-as-judge
- Stores Markdown + RAGAS scores in job result
- Rendered in React `/reason` page with confidence badges, source links, RAGAS score cards

---

## 6. Budget Controller

### Budget Oracle (`budget/oracle.py`)
- Async singleton consulted before every LLM call
- `can_afford(model, estimated_tokens)` — checks RPM (60s window), RPD (from headers), TPM (from headers), tokens-in-flight
- `resolve_model(task_type, model, tokens)` — walks fallback chain, returns cheapest capable model
- `gate(model, tokens)` → `(allowed, model_to_use)` — reserves tokens, acquires scheduler semaphore
- Prompt caching awareness: GPT-OSS models get 75% token cost reduction
- DynamoDB persistence: restores budget state on restart, saves snapshots

### Budget Register (`budget/register.py`)
- Per-model: RPM (internal sliding window, Groq doesn't expose), RPD (from `x-ratelimit-remaining-requests`), TPM (from `x-ratelimit-remaining-tokens`)
- `tokens_in_flight` tracking prevents overcommit
- 6 Groq models tracked

### Leaky Bucket Scheduler (`budget/scheduler.py`)
- Per-model asyncio semaphores: Scout=4, 8B/70B/20B=2, 120B=1
- Exponential backoff + jitter on contention

### Fallback Chains (`budget/fallback_chains.yaml`)
- Per-task sequences: decomposition, classification, extraction, analysis, contradiction_detection, synthesis, critic
- Last resort always "local" (spaCy/BM25/rule-based)

---

## 7. InferenceProvider Protocol

Every model call goes through `InferenceProvider.generate(prompt: AssembledPrompt, config: InferenceConfig) → InferenceResult`. No node calls a provider directly.

- `providers/groq_provider.py` — Wraps GroqKeyManager, one instance per model
- `providers/local_provider.py` — spaCy/BM25 fallback when all API budgets exhausted
- (Gemini provider removed — pipeline uses Groq exclusively)

`AssembledPrompt` is the only accepted input — structurally enforced at the type level.

---

## 8. Prompt Assembly Layer (`prompt/assembler.py`)

Five layers assembled in order:
1. **System** (static, cached, never trimmed) — loaded from `prompt/roles/<role>.txt`
2. **Retrieval context** (optional, trimmed first when over budget)
3. **Tool schemas** (optional, trimmed before context)
4. **Dynamic task content** (never trimmed)
5. **Budget trim pass** — removes layers 3 then 2 if exceeding estimated token limit

GPT-OSS model system prompts are cached by Groq (zero TPM). Llama models pay full TPM for the entire prompt.

---

## 9. Retrieval Architecture

### 4-Tier Hybrid
1. **Neo4j KG** — spaCy NER → entity lookup → relationship traversal (zero tokens)
2. **Cross-session cache** — `WebResearchResult` nodes, cosine ≥ 0.85, 7-day TTL
3. **Vector + BM25** — gte-small Qdrant VectorStoreIndex + rank-bm25 keyword
4. **Session index** — in-memory LlamaIndex from current Crawl4AI content

### LlamaIndex Integration
- `VectorStoreIndex` backed by shared Qdrant `synapse_nodes` collection
- `SimpleKeywordTableIndex` via rank-bm25
- `KnowledgeGraphIndex` — spaCy entity extraction → Neo4j traversal
- Falls back to hand-rolled retrieval if llama-index not installed

### Query Engines (`retrieval/query_engines.py`)
- `query_vector(question)` — Qdrant cosine similarity
- `query_bm25(question)` — BM25 sparse retrieval
- `query_graph(entity)` — 2-hop Neo4j traversal
- `query_hybrid(question)` — weighted fusion (0.6 vector, 0.4 BM25)

---

## 10. V3.0 Gap Fixes (from audit)

| Issue | Fix |
|-------|-----|
| EmbeddingPipeline + SemanticSimilarityPass never called | Wired into `run_pipeline()` as stages 6-7 |
| WebhookDispatcher never called | Wired into `run_pipeline()` as stage 8 |
| `execute_with_rotation()` UnboundLocalError | Key tracked before client creation |
| FINE_TUNED_FROM, AUTHORED_BY, DEPENDS_ON extraction missing | Implemented in `relationships.py` |
| NL query missing `fact_tier` field | Added to all response paths |
| `CORS_ORIGINS` whitespace bug | Strip on split |
| `GROQ_MODELS_ENABLED` env var ignored | Now read from env |
| `weeky_archive.yml` was no-op | Full pipeline + Neo4j snapshot |
| `weekly_eval.yml` missing secrets | All DB secrets added, switched to `uv sync` |

---

## 11. API Endpoints

### v3.0 (unchanged)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | Live node/edge counts |
| GET | `/api/v1/whats-new` | New entities (N days) |
| GET | `/api/v1/search` | Full-text CONTAINS search |
| GET | `/api/v1/similar` | Top-k semantic similarity |
| GET | `/api/v1/export` | JSON-LD / CSV ZIP / GraphML |
| GET | `/api/v1/diff` | Temporal diff |
| GET | `/api/v1/leaderboard` | Top tools/papers/techniques |
| GET | `/api/v1/technique/{name}/ecosystem` | 2-hop graph |
| GET | `/api/v1/org/{name}/releases` | Org releases |
| GET | `/api/v1/model/{hf_id}/lineage` | Model lineage |
| POST | `/api/v1/query` | NL → Cypher translation |
| GET | `/api/v1/groq/status` | Key + model status |

### v4.0 (new)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/reason` | Submit deep reasoning query → returns job_id |
| GET | `/api/v1/reason/{job_id}` | Poll job status + result (with `ragas_eval` scores) |
| POST | `/api/v1/ingest` | Upload document for session indexing |
| GET | `/api/v1/budget` | Per-model budget status |
| GET | `/api/v1/eval` | RAGAS metrics (total_runs, averages, last_10) |
| POST | `/api/v1/webhook/subscribe` | HMAC-signed webhook subscriptions |

---

## 12. Node Types & Relationships

### Node Types (14 + 2 v4.0)
Paper, Model, Tool, Technique, TechniqueAlias, Organization, Author, Benchmark, BenchmarkResult, ChangelogEntry, EmbeddingIndex, ModelFamily, Release, WebhookSubscription, **BackgroundContent**, **WebResearchResult**

### Relationship Types (20)
AUTHORED_BY, PUBLISHED_BY, INTRODUCES, CITES, IMPLEMENTS, BASED_ON_PAPER, SUPPORTS_MODEL, FINE_TUNED_FROM, BENCHMARKS_ON, HAS_RESULT, DEPENDS_ON, SUCCESSOR_OF, ALIAS_OF, HAS_RELEASE, ADDS_SUPPORT_FOR, BELONGS_TO_FAMILY, COLLABORATES_WITH, DERIVED_SUPPORTS_MODEL, SEMANTICALLY_SIMILAR, SUPERSEDES

### Fact Tiers
T1 (highest — official API), T2 (extracted from text), T3 (inferred/derived), T4 (lowest), SYSTEM

---

## 13. RAGAS Evaluation

After each pipeline run, the output node evaluates retrieval quality using RAGAS (LLM-as-judge, Groq 8B):

| Metric | What it measures |
|--------|-----------------|
| Faithfulness | Does answer stay true to provided context? |
| Answer Relevancy | Does answer address the question? |
| Context Precision | Are retrieved documents relevant? |
| Context Recall | Were all relevant documents retrieved? |

Scores are tracked per-run (500-run window), exposed via `/api/v1/eval`, and displayed on the Quality page with color-coded score cards (green ≥ 80%, amber ≥ 50%, red < 50%).

---

## 14. Design Patterns

### v3.0 (retained)
Singleton, Factory, Strategy, Repository, Circuit Breaker, Observer/Event Bus, Command, Decorator, Facade

### v4.0 (new)
- **Token Budget Gate** — mandatory decorator on every LLM-preceding edge
- **InferenceProvider Protocol** — all model calls through same interface
- **Prompt Assembly as Mandatory Pre-inference** — structurally enforced at type level
- **Subagent Budget Inheritance** — parent allocates slice, child cannot exceed

### Graceful Degradation
Every external dependency has a fallback. No single failure crashes the pipeline:
- Neo4j offline → [] results
- Qdrant offline → [] results
- Groq key exhausted → walk fallback chain
- Crawl4AI not installed → aiohttp fallback
- CrewAI not installed → plain LangGraph node
- Tavily not configured → DuckDuckGo only
- MCP servers unavailable → placeholder stubs
- DynamoDB/SQS unreachable → in-memory fallback

---

## 15. Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| NEO4J_URI | Yes | Neo4j Aura connection |
| NEO4J_USERNAME | Yes | Neo4j username |
| NEO4J_PASSWORD | Yes | Neo4j password |
| NEO4J_DATABASE | Yes | Neo4j database name |
| GROQ_API_KEYS | Yes | Comma-separated Groq keys |
| POSTGRES_URL | No | Neon.dev PostgreSQL |
| QDRANT_URL | No | Qdrant Cloud URL |
| QDRANT_API_KEY | No | Qdrant API key |
| TAVILY_API_KEY | No | Tavily search (1,000 free/month) |
| ZENROWS_API_KEY | No | ZenRows anti-bot fallback |
| AWS_ACCESS_KEY_ID | No | DynamoDB + S3 + SQS |
| AWS_SECRET_ACCESS_KEY | No | DynamoDB + S3 + SQS |
| AWS_REGION | No | e.g., ap-south-1 |
| DYNAMODB_TABLE | No | synapse_jobs |
| SQS_QUEUE_URL | No | Reasoning job queue |
| MCP_MEMORY_PATH | No | Path to Memory MCP server |
| MCP_SEQUENTIAL_THINKING_PATH | No | Path to Sequential Thinking MCP |
| MCP_FILESYSTEM_PATH | No | Path to Filesystem MCP |
| CORS_ORIGINS | No | http://localhost:5173 |
| LOG_LEVEL | No | INFO |
| BUDGET_RPD_ALERT_THRESHOLD | No | 0.80 |
| CRAWL4AI_TIMEOUT | No | 30 |
| RETRIEVAL_CONFIDENCE_THRESHOLD | No | 0.65 |
| CRITIC_MAX_RETRIES | No | 2 |

---

## 16. CI/CD (GitHub Actions)

| Workflow | Schedule | Action |
|----------|----------|--------|
| `daily_ingest.yml` | 00:00 UTC | 9 API source ingestion (uv sync + pipeline run) |
| `background_scrape.yml` | Every 6h | 9-source curated content scrape (Crawl4AI + 5-gate verifier) |
| `weekly_archive.yml` | Sunday 01:00 | Full pipeline + Neo4j snapshot + artifact |
| `weekly_eval.yml` | Sunday 02:00 | pytest with DB secrets |

---

## 17. Live Test Results (May 2026)

```
Query: "How have the trade-offs of LoRA vs full fine-tuning evolved since 2022?"

Pipeline: 67.9s, status=COMPLETE
Models:  decomposition→gpt-oss-20b, extractor→llama-8b, analyzer→scout,
         contradiction→scout, synthesis→llama-70b, critic→gpt-oss-20b
Tokens:  6,340 total
Synthesis: 2,529 chars (structured Markdown with all 6 sections)

RAGAS Faithfulness:        0.889
RAGAS Answer Relevancy:    0.875
RAGAS Context Precision:   0.000  (No Neo4j/Qdrant online)
RAGAS Context Recall:      0.000  (No Neo4j/Qdrant online)
```

---

## 18. What Is Not In v4.0

- LaTeX report generation (removed — Markdown output only)
- Pandoc PDF export (removed)
- Gemini provider (removed — Groq-only pipeline)
- Self-evolution engine (deferred to v5.0)
- MCP server role (deferred to v5.0)
- Real-time streaming responses (job polling pattern)
- Multi-user concurrent sessions (SQS queues, one-at-a-time)
- Voice components (absent entirely)

---

*Built by Sarvesh Bhattacharyya, Bengaluru · May 2026*
