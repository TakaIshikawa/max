# max

## Vision
Generalized idea generation engine — transforms ecosystem signals into tact-compatible project specs.

## Built So Far
- Core pipeline: fetch signals from external sources, synthesize insights via LLM, ideate buildable units, evaluate with 7-dimension utility scoring, generate tact specs
- 8 source adapters: HackerNews, Reddit, NPM, PyPI, GitHub trending, GitHub Issues, Security Advisories, Product Hunt (plugin-based, entry-point discoverable)
- Meta-intelligence layer: signal role annotation (problem/solution/market), cross-source triangulation, adaptive fetch allocation, gap detection (validated unmet needs)
- Incremental synthesis with semantic deduplication (trigram-hash fallback embeddings)
- Evidence-grounded evaluation with full signal-to-insight-to-idea traceability
- Feedback loop: closed-loop weight adaptation from approval/rejection outcomes
- Ideation memory: existing ideas injected into prompts to avoid regeneration
- REST API (FastAPI) + MCP server (fastmcp) + scheduler with configurable intervals
- CLI with evaluation profiles, ideation modes, and feedback commands
- SQLite store with schema migrations (v1 → v2 → v3)
- 218 tests, all passing

## Latest
Added meta-intelligence e2e test covering signal roles, triangulation, gap detection, and prompt threading. Fixed test determinism by designing signals with shared content for hash-based trigram embedding clustering.

## Next
TBD
