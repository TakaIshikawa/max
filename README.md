# max

Generalized idea generation engine — transforms ecosystem signals into tact-compatible project specs.

Max ingests data from 8+ sources (HackerNews, Reddit, GitHub, NPM, PyPI, Product Hunt, security advisories), synthesizes patterns via Claude, generates scored buildable ideas, and exports specs for automated execution. A feedback loop adapts scoring weights over time.

## Architecture

```
Signals → Insights → BuildableUnits → Evaluation → TactSpecs → Publication
  (fetch)  (synthesize)  (ideate)       (score)      (generate)   (write/push)
```

**Pipeline stages** (orchestrated by `pipeline/runner.py`):

1. **Fetch** — Collect signals from adapters with circuit breakers and adaptive allocation
2. **Annotate** — Classify signals by role (problem / solution / market)
3. **Synthesize** — LLM converts signals into insights; deduplication via embeddings
4. **Detect gaps** — Identify unmet needs from feedback history
5. **Ideate** — LLM generates buildable units from insights (direct, refinement, cross-domain modes)
6. **Evaluate** — Score ideas on 7 dimensions; produce recommendation
7. **Generate spec** — Convert approved ideas to tact-compatible specs
8. **Publish** — Write to filesystem or push to tact daemon

Cross-cutting: triangulation (multi-source corroboration), retrospective learning, budget enforcement, incremental synthesis.

### Directory layout

```
src/max/
├── pipeline/       # Runner, scheduling, fetch allocation
├── sources/        # Adapter registry + 8 adapters (hackernews, reddit, github, …)
├── synthesis/      # Signal → Insight engine
├── ideation/       # Insight → BuildableUnit engine
├── evaluation/     # 7-dimension scoring engine
├── spec/           # Tact spec generation
├── publisher/      # File writer, API client
├── analysis/       # Gap detection, triangulation, retrospectives
├── types/          # Pydantic domain models
├── store/          # SQLite persistence (WAL, schema v8)
├── llm/            # Anthropic client, token tracking, budget
├── embeddings/     # Semantic similarity index
├── server/         # FastAPI REST API + MCP server
├── profiles/       # Profile schema and loader
└── cli.py          # Click CLI entry point
profiles/           # YAML domain profiles (devtools, healthcare, fintech, …)
tests/              # 53 test files covering all modules
```

## Key Features

- **Multi-source ingestion** — 8 pluggable adapters discovered via entry points; circuit breakers prevent cascading failures
- **Evidence traceability** — every spec traces back through units → insights → signals
- **Domain profiles** — YAML configs define sources, categories, evaluation weights, and target users per domain
- **Feedback-driven adaptation** — approval/rejection outcomes adjust scoring weights and fetch allocation
- **Budget enforcement** — token and cost limits with mid-pipeline checks
- **Incremental synthesis** — only processes new signals since last run

## API Overview

### Public types (`max.types`)

| Type | Description |
|------|-------------|
| `Signal` | Raw data point from an external source |
| `Insight` | Synthesized pattern with evidence chain |
| `BuildableUnit` | Concrete idea with problem/solution/stack |
| `UtilityEvaluation` | 7-dimension score + recommendation |
| `TactSpec` | tact-compatible project specification |

### CLI (`max`)

```
max run              # Execute full pipeline
max serve            # Start REST + MCP server
max ideas            # List generated ideas
max inspect <id>     # Show idea details with evidence chain
max review           # Interactive approval/rejection
max publish <id>     # Generate tact spec
max feedback <id>    # Record outcome
max profiles         # List available domain profiles
max trends           # Approval rate trends
max archive          # Archive old records
```

### REST API (FastAPI)

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/signals` | List signals (cursor-paginated) |
| `GET /api/v1/insights` | List insights (cursor-paginated) |
| `GET /api/v1/ideas` | List ideas (cursor-paginated) |
| `GET /api/v1/ideas/{id}` | Idea detail with evidence |
| `POST /api/v1/pipeline/run` | Trigger pipeline run |
| `PUT /api/v1/schedule` | Configure scheduler |

Includes CORS, security headers, and rate limiting middleware.

### MCP Server

Tools: `search_ideas`, `get_idea`, `get_spec`, `contribute_signal`, `contribute_idea`, `evaluate_idea`, `find_similar`, `get_stats`, `get_schedule`, `set_schedule`

Resources: `ideas://list`, `ideas://{id}`, `specs://{id}`

## Development

```bash
# requires Python >= 3.12
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# configure
cp .env.template .env  # set ANTHROPIC_API_KEY

# run tests
pytest

# lint
ruff check src/ tests/
```

### Environment variables

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Required — Claude API key |
| `MAX_PROFILE` | Default pipeline profile |
| `MAX_TOKEN_BUDGET` / `MAX_COST_BUDGET` | Budget limits |
| `MAX_SCHEDULE_INTERVAL` | Auto-run interval (seconds) |
| `MAX_RETENTION_DAYS` | Archive threshold |

## Direction

Current trajectory:

- **Resilience** — circuit breakers, retry with backoff, rate limiting, CORS/security headers
- **Observability** — pipeline run history, per-adapter quality metrics, token cost tracking
- **Feedback loop maturity** — gap detection, retrospective analysis, adaptive fetch allocation
- **Multi-surface access** — CLI, REST API, and MCP server for human and agent consumers
- **Domain expansion** — profile-driven configuration for new verticals (8 profiles currently)
