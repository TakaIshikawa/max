# Clearance Report

- Project: `/Users/taka/Project/experiments/max`
- Generated: `2026-04-24T04:25:46+00:00`
- Status: `blocked`

## Findings

### BLOCKER: Project license is missing

A public open source release needs an explicit top-level license file.

Remediation: Add a LICENSE file and align package metadata with it.

### WARNING: Third-party notices are missing

A public release should preserve third-party notices and attribution requirements where applicable.

Remediation: Add NOTICE or THIRD_PARTY_NOTICES.md after reviewing dependency licenses.

### BLOCKER: Potential secret-bearing file is present (`.env`)

.env commonly contains credentials and should not be published.

Remediation: Remove it from git, rotate exposed credentials if needed, and keep an example file instead.

### BLOCKER: Hardcoded Anthropic API key detected (`.env:1`)

Found potential hardcoded secret on line 1: sk-ant-api03--FZTqRbJfIYiNfl2tUSwm6ye9dG...[truncated]

Remediation: Remove hardcoded secrets. Use environment variables, secret management systems, or configuration files (excluded from git).

### BLOCKER: Hardcoded Bearer token detected (`.tact/agent-comms-firewall/architecture.yaml:84`)

Found potential hardcoded secret on line 84: Bearer tokens

Remediation: Remove hardcoded secrets. Use environment variables, secret management systems, or configuration files (excluded from git).

### WARNING: OpenAI usage detected outside dependency manifests (`.tact-experiments/cybersecurity/shadow-ai-dlp-agent/product.yaml`)

Source text references a known provider, environment variable, or tool name.

Remediation: Confirm applicable provider terms, data handling, examples, and publication requirements.

### WARNING: Anthropic policy review required

The project appears to use Anthropic. Review current provider terms before public release.

Remediation: Record review owner, date, account type, applicable terms, and any required safeguards in the release decision.

### WARNING: OpenAI policy review required

The project appears to use OpenAI. Review current provider terms before public release.

Remediation: Record review owner, date, account type, applicable terms, and any required safeguards in the release decision.

### INFO: Policy monitoring sources configured

5 provider policy sources are available for snapshot monitoring.

Remediation: Run `clearance monitor` before release and on a schedule after publication.

## Dependencies

| Name | Version | License | Provider | Source |
| --- | --- | --- | --- | --- |
| anthropic | >=0.42.0 |  | Anthropic | pyproject.toml:project.dependencies |
| httpx | >=0.27.0 |  |  | pyproject.toml:project.dependencies |
| pydantic | >=2.0 |  |  | pyproject.toml:project.dependencies |
| click | >=8.0 |  |  | pyproject.toml:project.dependencies |
| python-dotenv | >=1.0 |  |  | pyproject.toml:project.dependencies |
| pyyaml | >=6.0 |  |  | pyproject.toml:project.dependencies |
| fastapi | >=0.115.0 |  |  | pyproject.toml:project.dependencies |
| uvicorn | [standard]>=0.32.0 |  |  | pyproject.toml:project.dependencies |
| fastmcp | >=2.0 |  |  | pyproject.toml:project.dependencies |
| pytest | >=8.0 |  |  | pyproject.toml:project.optional-dependencies.dev |
| pytest-asyncio | >=0.24 |  |  | pyproject.toml:project.optional-dependencies.dev |
| ruff | >=0.8.0 |  |  | pyproject.toml:project.optional-dependencies.dev |

## Policy Sources

- **OpenAI: Terms and policies index**
  - URL: https://openai.com/policies
  - Review: Review applicable Terms of Use, Service Terms, privacy, publication, and usage policy pages before release.
- **OpenAI: Usage policies**
  - URL: https://openai.com/policies/usage-policies/
  - Review: Confirm the project use case, examples, tests, and documentation do not encourage prohibited or high-risk use without required safeguards.
- **OpenAI: Service terms**
  - URL: https://openai.com/policies/service-terms
  - Review: Review API-specific terms, output handling, indemnity exclusions, and third-party offering language.
- **Anthropic: Claude Code data usage**
  - URL: https://docs.anthropic.com/en/docs/claude-code/data-usage
  - Review: Confirm account type, telemetry, bug reporting, data retention, and model training settings before publishing code or examples.
- **Anthropic: Usage policy update**
  - URL: https://www.anthropic.com/news/usage-policy-update
  - Review: Use as a pointer to current Anthropic usage policy expectations, especially agentic, cybersecurity, and high-risk use cases.

## Repository Configuration

### Gitignore

Add these patterns to `.gitignore` to avoid committing generated reports and private review notes:

```gitignore
# Publication clearance
clearance-report/
.clearance/AI_PROVIDER_REVIEW.md
```

Commit these files to enable ongoing monitoring:

- `.clearance/policy-snapshots.json` - Policy hash baselines
- `.clearance/README.md` - Monitoring documentation

---

## Next Steps

For detailed review guidance, see:
- [Release Checklist](https://github.com/anthropics/clearance/blob/main/references/release-checklist.md)
- Run `clearance monitor` to establish policy baselines
