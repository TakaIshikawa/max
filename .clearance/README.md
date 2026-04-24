# Publication Clearance Configuration

This directory contains baseline data for publication clearance monitoring.

## Files

### `policy-snapshots.json` (committed)
Baseline snapshots of AI provider policy pages. This file is committed to the repository to enable ongoing monitoring of policy changes.

When the monitor detects a change, human review is required before accepting the new baseline.

### `AI_PROVIDER_REVIEW.md` (gitignored - private)
Private review documentation capturing AI provider policy compliance decisions. This file contains internal review notes and should **not be committed** to the public repository.

## Monitoring

Run policy monitoring periodically to detect provider policy changes:

```bash
# If clearance is installed:
clearance monitor --project . --report-dir clearance-report

# Or from clearance source repository:
cd /path/to/clearance
PYTHONPATH=src python -m clearance monitor --project /path/to/your-repo --report-dir clearance-report
```

### When a Policy Change is Detected

1. Review the changed policy page URL
2. Assess impact on your codebase, examples, and documentation
3. Update code, docs, or account configuration if needed
4. Commit the new snapshot only after review is complete

## Gitignore Configuration

Add to your `.gitignore`:

```gitignore
# Publication clearance
clearance-report/
.clearance/AI_PROVIDER_REVIEW.md
```

**Commit these files:**
- `.clearance/policy-snapshots.json` - Policy hash baselines
- `.clearance/README.md` - This file

## GitHub Actions

For automated monitoring, add a scheduled workflow:

```bash
clearance init-github-action --project .
```

Review and commit the generated `.github/workflows/clearance.yml` file.
