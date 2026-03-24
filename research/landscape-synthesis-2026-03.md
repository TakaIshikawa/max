# Max Research: "Things Worth Building" Landscape (March 2026)

## Three Macro Categories of High-Utility Work

### Category A: Agent Infrastructure (tools FOR agents)
| Opportunity | Gap Severity | Signal |
|---|---|---|
| Verification/evaluation automation | Critical | Generation outpaces review 10x; 96% don't trust AI code |
| Context budget management | Critical | 50 MCP tools = 100K+ tokens wasted before conversation starts |
| Cross-session memory | Critical | 5+ competing solutions (Mem0, Zep, Letta, Hindsight), no winner |
| Semantic conflict resolution | Critical | Git worktrees = workaround; semantic contradictions slip past |
| Agent cost management / FinOps | High | 60-70% of spend is wasted context; no standard metering |
| Architectural enforcement | High | 39% more code churn, 8x duplication in AI-heavy projects |
| Blast radius estimation | High | 30% of agent runs hit exceptions needing recovery |

### Category B: Agent-Consumable Services (tools agents USE)
| Opportunity | Gap Severity | Signal |
|---|---|---|
| Healthcare MCP (FHIR/EHR) | Entire vertical unserved | 16K servers, zero for healthcare |
| Unified CI/CD abstraction | Fragmented | Top MCP use case, no normalized interface |
| IoT / device management | Empty category | Industrial + consumer IoT untouched |
| Enterprise data harmonization | Critical for enterprise | SAP + Salesforce + Workday = siloed |
| API-to-MCP conversion | 76% of APIs not agent-ready | Every SaaS needs this |
| MCP security scanning | 66% of servers have vulns | Trust infrastructure missing |
| MCP quality certification | 16K servers, no quality signal | "npm circa 2016" problem |

### Category C: Human Productivity (tools for the orchestrator)
| Opportunity | Gap Severity | Signal |
|---|---|---|
| "What to build" decision engine | **Completely missing** | No tool connects signal to spec |
| Feedback-to-spec automation | Completely missing | User behavior → prioritized spec = 100% manual |
| Multi-project portfolio dashboard | Underserved for solo devs | Enterprise tools exist, nothing for 1-5 person |
| Spec-driven development toolchain | Nascent (Kiro, Spec Kit) | Root cause of AI code quality issues |
| Adaptive approval thresholds | Binary modes only | Risk-aware gating doesn't exist |

## Signal Sources for Max
| Source Type | Specific Sources | Signal Quality |
|---|---|---|
| Ecosystem registries | MCP registry (16K), npm (2.4K MCP), awesome-lists | Gaps by category coverage |
| Developer surveys | Stack Overflow (65K), JetBrains (24K), GitHub Octoverse | Pain points quantified |
| Security reports | AgentSeal, Apiiro, Snyk, NIST | Vulnerability = opportunity |
| Protocol roadmaps | MCP 2026 roadmap, A2A spec, AAIF | What's coming = what to build for |
| Agent failure data | Devin reviews, SWE-bench vs reality, incidents | Failure patterns = tooling gaps |
| Benchmark gaps | MCPBench, SWE-bench limitations, METR | What can't be measured = needs tools |
| Funding signals | $73M in MCP ecosystem, $300M Browserbase | Money flow = validated demand |
| Forum complaints | Reddit, HN, DEV.to, SO questions | Direct pain expression |

## Utility Scoring Dimensions
1. **Pain severity** -- How acute is the problem? (surveys, complaints, incident data)
2. **Addressable scale** -- How many humans + agents would use this?
3. **Build effort** -- Tokens/hours to useful v1?
4. **Composability** -- MCP/A2A compatible >> standalone app
5. **Competitive density** -- How many solutions exist? (0 = greenfield)
6. **Timing fit** -- Protocol/platform mature enough to build on?
7. **Compounding value** -- Does this unblock other things?

## Key Statistics
| Metric | Value | Source |
|---|---|---|
| MCP servers registered | 16,000+ | Glama, registries |
| MCP monthly SDK downloads | 97M+ | PyPI + npm |
| Servers with security findings | 66% | AgentSeal scan of 1,808 |
| Developers not trusting AI code | 96% | SRLabs |
| AI code verification gap | 48% don't verify before commit | SRLabs |
| Code churn increase (AI projects) | +39% | GitClear |
| AI-generated PR review wait | 4.6x longer than human | SRLabs |
| Security findings increase (Fortune 50) | 10x in 6 months | Apiiro |
| Agent runs needing recovery | 30% | Multiple sources |
| 10-step workflow success (85%/step) | ~20% | TDS |
| AI agent ecosystem investment | $73M+ (MCP alone) | Glama |
| Devs believing faster but actually slower | +20% perceived, -19% actual | METR |
