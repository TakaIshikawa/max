# max

## Vision
Generalized idea generation engine — transforms ecosystem signals into tact-compatible project specs.

## Built So Far
- Core pipeline: fetch signals from external sources, synthesize insights via LLM, ideate buildable units, evaluate with 7-dimension utility scoring, generate tact specs
- 8 source adapters: HackerNews, Reddit, NPM, PyPI, GitHub trending, GitHub Issues, Security Advisories, Product Hunt (plugin-based, entry-point discoverable)
- Meta-intelligence layer: signal role annotation (problem/solution/market), cross-source triangulation, adaptive fetch allocation, gap detection (validated unmet needs)
- Incremental synthesis with semantic deduplication (trigram-hash fallback embeddings)
- Evidence-grounded evaluation with full signal-to-insight-to-idea traceability
- Feedback loop: closed-loop weight adaptation from approval/rejection outcomes, attribution tracking (feedback → idea → signals → adapters), feedback-aware fetch allocation, retrospective prompt learning
- Pipeline run persistence: pipeline_runs table tracks all metrics per run
- Ideation memory: existing ideas injected into prompts to avoid regeneration
- REST API (FastAPI) + MCP server (fastmcp) + scheduler with configurable intervals
- CLI with evaluation profiles, ideation modes, and feedback commands
- SQLite store with schema migrations (v1 → v2 → v3 → v4)
- 315 tests, all passing

## Latest
Added 3-layer feedback loop: (1) attribution tracking with pipeline run persistence (schema v4), (2) feedback-aware fetch allocation that blends utilization with approval rates, (3) retrospective analysis extracting learned patterns (successful categories, adapters, target users) injected into ideation prompts.

## Next
TBD
