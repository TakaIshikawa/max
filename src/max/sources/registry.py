"""Adapter registry — discover and instantiate source adapters.

Adapters are discovered via entry_points (group: max.adapters) for installed
packages, with a fallback to built-in imports for dev mode.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import logging
from dataclasses import dataclass

from max.sources.base import SourceAdapter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdapterMetadata:
    """Human-readable adapter configuration metadata."""

    name: str
    config_keys: list[str]
    required_keys: list[str]
    description: str

    @property
    def supported_config_keys(self) -> list[str]:
        """Alias for callers that prefer the full metadata term."""
        return self.config_keys


# Fallback mapping for dev mode (when package is not pip-installed).
_BUILTIN_ADAPTERS: dict[str, str] = {
    "hackernews": "max.sources.hackernews:HackerNewsAdapter",
    "npm_registry": "max.sources.npm_registry:NpmRegistryAdapter",
    "reddit": "max.sources.reddit:RedditAdapter",
    "github": "max.sources.github:GitHubAdapter",
    "github_releases": "max.sources.github_releases:GitHubReleasesAdapter",
    "github_funding": "max.sources.github_funding:GitHubFundingAdapter",
    "funding_rounds": "max.sources.funding_rounds:FundingRoundsAdapter",
    "pypi_registry": "max.sources.pypi_registry:PyPIRegistryAdapter",
    "pypi_download_trends": (
        "max.sources.pypi_download_trends:PyPIDownloadTrendsAdapter"
    ),
    "github_issues": "max.sources.github_issues:GitHubIssuesAdapter",
    "github_pull_requests": "max.sources.github_pull_requests:GitHubPullRequestsAdapter",
    "github_actions": "max.sources.github_actions:GitHubActionsAdapter",
    "github_octoverse": "max.sources.github_octoverse:GitHubOctoverseAdapter",
    "snyk_reports": "max.sources.snyk_reports:SnykReportsAdapter",
    "agentseal_mcp_scan": "max.sources.agentseal_mcp_scan:AgentSealMcpScanAdapter",
    "ai_code_trust_reports": (
        "max.sources.ai_code_trust_reports:AICodeTrustReportsAdapter"
    ),
    "metr_productivity_reports": (
        "max.sources.metr_productivity_reports:MetrProductivityReportsAdapter"
    ),
    "agent_failure_dataset": "max.sources.agent_failure_dataset:AgentFailureDatasetAdapter",
    "github_discussions": "max.sources.github_discussions:GitHubDiscussionsAdapter",
    "gitlab_issues": "max.sources.gitlab_issues:GitLabIssuesAdapter",
    "gitlab_merge_requests": "max.sources.gitlab_merge_requests:GitLabMergeRequestsAdapter",
    "gitlab_releases": "max.sources.gitlab_releases:GitLabReleasesAdapter",
    "bitbucket_pull_requests": "max.sources.bitbucket_pull_requests:BitbucketPullRequestsAdapter",
    "security_advisories": "max.sources.security_advisories:SecurityAdvisoriesAdapter",
    "osv_vulnerabilities": "max.sources.osv_vulnerabilities:OsvVulnerabilitiesAdapter",
    "cisa_kev": "max.sources.cisa_kev:CisaKevAdapter",
    "nvd_cve": "max.sources.nvd_cve:NvdCveAdapter",
    "product_hunt": "max.sources.product_hunt:ProductHuntAdapter",
    "stackexchange": "max.sources.stackexchange:StackExchangeAdapter",
    "stackoverflow": "max.sources.stackoverflow:StackOverflowAdapter",
    "stackoverflow_survey": "max.sources.stackoverflow_survey:StackOverflowSurveyAdapter",
    "jetbrains_survey": "max.sources.jetbrains_survey:JetBrainsSurveyAdapter",
    "discourse": "max.sources.discourse:DiscourseAdapter",
    "arxiv": "max.sources.arxiv:ArxivAdapter",
    "openalex": "max.sources.openalex:OpenAlexAdapter",
    "devto": "max.sources.devto:DevtoAdapter",
    "bluesky": "max.sources.bluesky:BlueskyAdapter",
    "mastodon": "max.sources.mastodon:MastodonAdapter",
    "pubmed": "max.sources.pubmed:PubMedAdapter",
    "clinical_trials": "max.sources.clinical_trials:ClinicalTrialsAdapter",
    "rss_feed": "max.sources.rss_feed:RssFeedAdapter",
    "crates_io": "max.sources.crates_io:CratesIoAdapter",
    "lobsters": "max.sources.lobsters:LobstersAdapter",
    "nuget": "max.sources.nuget:NuGetAdapter",
    "maven_central": "max.sources.maven_central:MavenCentralAdapter",
    "rubygems": "max.sources.rubygems:RubyGemsAdapter",
    "packagist": "max.sources.packagist:PackagistAdapter",
    "dockerhub": "max.sources.dockerhub:DockerHubAdapter",
    "homebrew_formulae": "max.sources.homebrew_formulae:HomebrewFormulaeAdapter",
    "mcp_registry": "max.sources.mcp_registry:McpRegistryAdapter",
    "mcp_protocol_roadmap": (
        "max.sources.mcp_protocol_roadmap:McpProtocolRoadmapAdapter"
    ),
    "glama_mcp_stats": "max.sources.glama_mcp_stats:GlamaMcpStatsAdapter",
    "stackshare": "max.sources.stackshare:StackShareAdapter",
    "huggingface": "max.sources.huggingface:HuggingFaceAdapter",
    "awesome_lists": "max.sources.awesome_lists:AwesomeListsAdapter",
    "openssf_scorecard": "max.sources.openssf_scorecard:OpenSSFScorecardAdapter",
    "cncf_landscape": "max.sources.cncf_landscape:CncfLandscapeAdapter",
    "chrome_web_store": "max.sources.chrome_web_store:ChromeWebStoreAdapter",
    "open_vsx": "max.sources.open_vsx:OpenVsxAdapter",
    "vscode_marketplace": "max.sources.vscode_marketplace:VSCodeMarketplaceAdapter",
    "figma_community": "max.sources.figma_community:FigmaCommunityAdapter",
    "terraform_registry": "max.sources.terraform_registry:TerraformRegistryAdapter",
    "go_packages": "max.sources.go_packages:GoPackagesAdapter",
    "kubernetes_keps": "max.sources.kubernetes_keps:KubernetesKepsAdapter",
    "apis_guru": "max.sources.apis_guru:ApisGuruAdapter",
    "federal_register_healthcare": (
        "max.sources.federal_register_healthcare:FederalRegisterHealthcareAdapter"
    ),
    "a2a_spec": "max.sources.a2a_spec:A2ASpecAdapter",
}

_BUILTIN_ADAPTER_METADATA: dict[str, AdapterMetadata] = {
    "hackernews": AdapterMetadata(
        name="hackernews",
        config_keys=["filter_keywords"],
        required_keys=[],
        description="Fetches Hacker News stories and optionally filters them by keywords.",
    ),
    "npm_registry": AdapterMetadata(
        name="npm_registry",
        config_keys=["queries"],
        required_keys=[],
        description="Searches the npm registry for packages matching configured query terms.",
    ),
    "reddit": AdapterMetadata(
        name="reddit",
        config_keys=["subreddits"],
        required_keys=[],
        description="Fetches posts from configured public subreddit names.",
    ),
    "github": AdapterMetadata(
        name="github",
        config_keys=["topics"],
        required_keys=[],
        description="Searches GitHub repositories for configured topics.",
    ),
    "github_releases": AdapterMetadata(
        name="github_releases",
        config_keys=[
            "repositories",
            "include_drafts",
            "include_prereleases",
            "github_token",
            "token",
        ],
        required_keys=[],
        description="Fetches release notes from configured GitHub repositories.",
    ),
    "github_funding": AdapterMetadata(
        name="github_funding",
        config_keys=["repositories", "github_token", "token"],
        required_keys=[],
        description="Fetches funding and sponsorship links from configured GitHub repositories.",
    ),
    "funding_rounds": AdapterMetadata(
        name="funding_rounds",
        config_keys=[
            "local_paths",
            "dataset_urls",
            "format",
            "sectors",
            "min_amount_usd",
            "max_rows",
        ],
        required_keys=[],
        description="Reads CSV, JSON, and JSONL funding round datasets as market validation signals.",
    ),
    "pypi_registry": AdapterMetadata(
        name="pypi_registry",
        config_keys=["keywords"],
        required_keys=[],
        description="Fetches PyPI package signals matching configured keywords.",
    ),
    "pypi_download_trends": AdapterMetadata(
        name="pypi_download_trends",
        config_keys=["packages", "period", "max_items", "min_downloads"],
        required_keys=[],
        description="Fetches recent PyPI package download trend totals as market adoption signals.",
    ),
    "github_issues": AdapterMetadata(
        name="github_issues",
        config_keys=["queries"],
        required_keys=[],
        description="Searches GitHub issues for configured query strings.",
    ),
    "github_pull_requests": AdapterMetadata(
        name="github_pull_requests",
        config_keys=[
            "queries",
            "repositories",
            "labels",
            "state",
            "min_comments",
            "max_age_days",
            "github_token",
            "token",
            "token_env",
        ],
        required_keys=[],
        description="Fetches GitHub pull request threads from configured repositories and search queries.",
    ),
    "github_actions": AdapterMetadata(
        name="github_actions",
        config_keys=[
            "repositories",
            "workflow_names",
            "workflows",
            "statuses",
            "status",
            "conclusions",
            "max_age_days",
            "token_env",
            "github_token",
            "token",
        ],
        required_keys=[],
        description="Fetches GitHub Actions workflow failures from configured repositories.",
    ),
    "github_octoverse": AdapterMetadata(
        name="github_octoverse",
        config_keys=["report_urls", "local_paths", "sections", "keywords", "max_items"],
        required_keys=[],
        description="Reads GitHub Octoverse-style Markdown and JSON reports as ecosystem trend signals.",
    ),
    "snyk_reports": AdapterMetadata(
        name="snyk_reports",
        config_keys=["report_urls", "local_paths", "sections", "keywords", "max_items"],
        required_keys=[],
        description=(
            "Reads Snyk-style Markdown and JSON security research reports as "
            "normalized vulnerability, dependency, and supply-chain signals."
        ),
    ),
    "agentseal_mcp_scan": AdapterMetadata(
        name="agentseal_mcp_scan",
        config_keys=[
            "local_paths",
            "report_urls",
            "severity_min",
            "categories",
            "max_items",
            "include_remediated",
        ],
        required_keys=[],
        description=(
            "Reads AgentSeal-style MCP server security scan JSON and JSONL exports "
            "as vulnerability, trust, and remediation signals."
        ),
    ),
    "mcp_protocol_roadmap": AdapterMetadata(
        name="mcp_protocol_roadmap",
        config_keys=[
            "roadmap_urls",
            "local_paths",
            "sections",
            "keywords",
            "max_items",
            "format",
        ],
        required_keys=[],
        description=(
            "Reads MCP protocol roadmap Markdown and JSON material as normalized "
            "capability, milestone, and protocol evolution signals."
        ),
    ),
    "ai_code_trust_reports": AdapterMetadata(
        name="ai_code_trust_reports",
        config_keys=[
            "report_urls",
            "local_paths",
            "sections",
            "keywords",
            "min_percent",
            "max_items",
        ],
        required_keys=[],
        description=(
            "Reads AI coding trust, verification, review latency, security, "
            "and productivity statistics from Markdown and JSON reports."
        ),
    ),
    "metr_productivity_reports": AdapterMetadata(
        name="metr_productivity_reports",
        config_keys=[
            "report_urls",
            "local_paths",
            "sections",
            "keywords",
            "metric_names",
            "max_items",
            "format",
        ],
        required_keys=[],
        description=(
            "Reads METR-style AI productivity and developer workflow Markdown "
            "and JSON reports as measured productivity evidence signals."
        ),
    ),
    "agent_failure_dataset": AdapterMetadata(
        name="agent_failure_dataset",
        config_keys=[
            "local_paths",
            "dataset_urls",
            "format",
            "failure_type_filters",
            "min_severity",
            "max_rows",
        ],
        required_keys=[],
        description="Reads agent benchmark and incident failure datasets as normalized failure_data signals.",
    ),
    "github_discussions": AdapterMetadata(
        name="github_discussions",
        config_keys=[
            "repositories",
            "categories",
            "labels",
            "search_terms",
            "include_answered",
            "max_age_days",
            "token_env",
            "github_token",
            "token",
        ],
        required_keys=[],
        description="Fetches GitHub Discussions threads from configured repositories.",
    ),
    "gitlab_issues": AdapterMetadata(
        name="gitlab_issues",
        config_keys=["queries", "labels", "project_ids", "state", "min_upvotes"],
        required_keys=[],
        description="Searches public GitLab issues for configured query strings and filters.",
    ),
    "gitlab_merge_requests": AdapterMetadata(
        name="gitlab_merge_requests",
        config_keys=[
            "project_ids",
            "queries",
            "labels",
            "state",
            "min_upvotes",
            "max_age_days",
            "gitlab_base_url",
            "token_env",
        ],
        required_keys=[],
        description="Fetches GitLab merge request review threads and metadata from configured projects and search queries.",
    ),
    "gitlab_releases": AdapterMetadata(
        name="gitlab_releases",
        config_keys=[
            "projects",
            "gitlab_base_url",
            "token_env",
            "include_prerelease",
            "max_age_days",
            "tags",
            "query_terms",
        ],
        required_keys=["projects"],
        description="Fetches release activity from configured GitLab projects.",
    ),
    "bitbucket_pull_requests": AdapterMetadata(
        name="bitbucket_pull_requests",
        config_keys=[
            "repositories",
            "workspace",
            "repository",
            "repository_slugs",
            "state",
            "states",
            "query",
            "q",
            "bitbucket_token",
            "token",
            "token_env",
        ],
        required_keys=[],
        description="Fetches Bitbucket Cloud pull request review threads from configured repositories.",
    ),
    "security_advisories": AdapterMetadata(
        name="security_advisories",
        config_keys=["ecosystems", "severities"],
        required_keys=[],
        description="Fetches GitHub Security Advisory signals by ecosystem and severity.",
    ),
    "osv_vulnerabilities": AdapterMetadata(
        name="osv_vulnerabilities",
        config_keys=[
            "ecosystems",
            "packages",
            "queries",
            "severity_min",
            "modified_since_days",
            "max_items",
        ],
        required_keys=[],
        description="Fetches OSV.dev package vulnerability signals by package or ecosystem.",
    ),
    "cisa_kev": AdapterMetadata(
        name="cisa_kev",
        config_keys=[
            "keywords",
            "vendors",
            "products",
            "max_age_days",
            "known_ransomware_campaign_use",
            "catalog_url",
        ],
        required_keys=[],
        description="Fetches CISA Known Exploited Vulnerabilities catalog signals.",
    ),
    "nvd_cve": AdapterMetadata(
        name="nvd_cve",
        config_keys=["keywords", "severities", "cvss_min", "max_age_days", "api_key_env"],
        required_keys=[],
        description="Fetches recent NVD CVE vulnerability signals matching configured filters.",
    ),
    "product_hunt": AdapterMetadata(
        name="product_hunt",
        config_keys=["topics"],
        required_keys=[],
        description="Fetches Product Hunt posts for configured topic slugs.",
    ),
    "stackexchange": AdapterMetadata(
        name="stackexchange",
        config_keys=["sites", "tags", "queries", "max_age_days", "min_score"],
        required_keys=[],
        description=(
            "Fetches recent Stack Exchange questions across configured sites, tags, "
            "query terms, age, and score filters."
        ),
    ),
    "stackoverflow": AdapterMetadata(
        name="stackoverflow",
        config_keys=["tags", "min_score", "unanswered_only"],
        required_keys=[],
        description="Fetches Stack Overflow questions for configured tags and score filters.",
    ),
    "stackoverflow_survey": AdapterMetadata(
        name="stackoverflow_survey",
        config_keys=["survey_urls", "local_paths", "question_filters", "min_percent", "max_rows"],
        required_keys=[],
        description="Reads Stack Overflow developer survey CSV exports as quantified market signals.",
    ),
    "jetbrains_survey": AdapterMetadata(
        name="jetbrains_survey",
        config_keys=[
            "survey_urls",
            "local_paths",
            "question_filters",
            "min_percent",
            "max_rows",
            "year",
        ],
        required_keys=[],
        description=(
            "Reads JetBrains Developer Ecosystem survey CSV exports as quantified market "
            "and developer-pain signals."
        ),
    ),
    "discourse": AdapterMetadata(
        name="discourse",
        config_keys=["base_urls", "category_slugs", "tags", "max_pages"],
        required_keys=["base_urls"],
        description="Fetches public Discourse forum topics from latest or category JSON endpoints.",
    ),
    "arxiv": AdapterMetadata(
        name="arxiv",
        config_keys=["categories", "queries"],
        required_keys=[],
        description="Fetches arXiv papers matching configured categories and query expressions.",
    ),
    "openalex": AdapterMetadata(
        name="openalex",
        config_keys=[
            "search_terms",
            "concepts",
            "from_publication_date",
            "per_page",
            "mailto",
        ],
        required_keys=[],
        description="Fetches scholarly works from OpenAlex matching configured search and concept filters.",
    ),
    "devto": AdapterMetadata(
        name="devto",
        config_keys=["tags", "period"],
        required_keys=[],
        description="Fetches DEV Community articles for configured tags and time period.",
    ),
    "bluesky": AdapterMetadata(
        name="bluesky",
        config_keys=["queries", "domains"],
        required_keys=[],
        description="Fetches recent Bluesky posts matching configured search terms.",
    ),
    "mastodon": AdapterMetadata(
        name="mastodon",
        config_keys=[
            "instances",
            "hashtags",
            "accounts",
            "exclude_reblogs",
            "min_favourites",
            "max_age_days",
            "access_token_env",
        ],
        required_keys=[],
        description="Fetches public Mastodon hashtag and account timeline signals.",
    ),
    "pubmed": AdapterMetadata(
        name="pubmed",
        config_keys=["queries", "max_results_per_query", "recent_days"],
        required_keys=[],
        description="Fetches PubMed article signals matching configured search queries.",
    ),
    "clinical_trials": AdapterMetadata(
        name="clinical_trials",
        config_keys=[
            "terms",
            "conditions",
            "intervention_terms",
            "interventions",
            "max_results_per_query",
        ],
        required_keys=[],
        description="Fetches ClinicalTrials.gov study records for healthcare validation and unmet-need signals.",
    ),
    "rss_feed": AdapterMetadata(
        name="rss_feed",
        config_keys=["feeds", "tags", "max_age_days"],
        required_keys=["feeds"],
        description="Fetches RSS or Atom entries from explicitly configured feed URLs.",
    ),
    "crates_io": AdapterMetadata(
        name="crates_io",
        config_keys=["queries", "categories"],
        required_keys=[],
        description="Searches Crates.io for Rust packages matching configured queries and categories.",
    ),
    "lobsters": AdapterMetadata(
        name="lobsters",
        config_keys=["tags", "page", "limit"],
        required_keys=[],
        description="Fetches Lobsters developer forum stories from newest or tag-specific JSON pages.",
    ),
    "nuget": AdapterMetadata(
        name="nuget",
        config_keys=["queries", "package_names", "include_prerelease"],
        required_keys=[],
        description="Fetches NuGet package metadata and recent version activity for configured packages and search terms.",
    ),
    "maven_central": AdapterMetadata(
        name="maven_central",
        config_keys=["queries", "coordinates"],
        required_keys=[],
        description="Fetches Maven Central Java/JVM package metadata for configured coordinates and search terms.",
    ),
    "rubygems": AdapterMetadata(
        name="rubygems",
        config_keys=["queries", "max_pages"],
        required_keys=[],
        description="Searches RubyGems for Ruby packages matching configured query terms.",
    ),
    "packagist": AdapterMetadata(
        name="packagist",
        config_keys=["queries", "include_maintenance", "active_release_days"],
        required_keys=[],
        description="Searches Packagist for PHP packages and release maintenance signals.",
    ),
    "dockerhub": AdapterMetadata(
        name="dockerhub",
        config_keys=["repositories", "queries", "include_tags"],
        required_keys=[],
        description="Fetches Docker Hub container image popularity and update signals for configured repositories and search terms.",
    ),
    "homebrew_formulae": AdapterMetadata(
        name="homebrew_formulae",
        config_keys=[
            "formulae_url",
            "casks_url",
            "include_casks",
            "queries",
            "categories",
            "min_install_count",
        ],
        required_keys=[],
        description="Fetches Homebrew formula and cask package popularity and update signals.",
    ),
    "mcp_registry": AdapterMetadata(
        name="mcp_registry",
        config_keys=["base_url", "endpoint", "queries", "categories", "min_stars", "min_score"],
        required_keys=[],
        description="Fetches MCP server registry discovery, package, capability, and trust signals.",
    ),
    "glama_mcp_stats": AdapterMetadata(
        name="glama_mcp_stats",
        config_keys=["stats_urls", "local_paths", "categories", "min_server_count", "max_items"],
        required_keys=[],
        description=(
            "Reads Glama-style MCP ecosystem aggregate growth, category, trust, "
            "funding, and adoption stats from JSON or Markdown reports."
        ),
    ),
    "stackshare": AdapterMetadata(
        name="stackshare",
        config_keys=["stacks", "categories", "base_url"],
        required_keys=[],
        description="Fetches StackShare developer tool and infrastructure adoption signals.",
    ),
    "huggingface": AdapterMetadata(
        name="huggingface",
        config_keys=["queries", "resource_types", "sort", "limit_per_query"],
        required_keys=[],
        description="Fetches Hugging Face Hub model, dataset, and Space discovery signals.",
    ),
    "awesome_lists": AdapterMetadata(
        name="awesome_lists",
        config_keys=["lists", "topics", "include_descriptions", "github_token"],
        required_keys=[],
        description="Fetches curated GitHub awesome-list markdown links as registry signals.",
    ),
    "openssf_scorecard": AdapterMetadata(
        name="openssf_scorecard",
        config_keys=[
            "repositories",
            "min_risk_score",
            "checks",
            "token",
            "token_env",
            "local_path",
            "local_paths",
        ],
        required_keys=[],
        description="Fetches OpenSSF Scorecard repository trust and supply-chain risk signals.",
    ),
    "cncf_landscape": AdapterMetadata(
        name="cncf_landscape",
        config_keys=[
            "landscape_urls",
            "local_paths",
            "categories",
            "maturity_levels",
            "include_archived",
            "min_stars",
        ],
        required_keys=[],
        description="Fetches CNCF Landscape-style cloud-native project adoption and maturity signals.",
    ),
    "chrome_web_store": AdapterMetadata(
        name="chrome_web_store",
        config_keys=["queries", "categories", "min_rating", "min_users", "max_items"],
        required_keys=[],
        description=(
            "Searches the Chrome Web Store for browser extension install, rating, "
            "category, publisher, and workflow adoption signals."
        ),
    ),
    "open_vsx": AdapterMetadata(
        name="open_vsx",
        config_keys=["queries", "extensions", "extension_identifiers"],
        required_keys=[],
        description="Searches Open VSX Registry for VS Code-compatible extension adoption signals.",
    ),
    "vscode_marketplace": AdapterMetadata(
        name="vscode_marketplace",
        config_keys=[
            "queries",
            "extensions",
            "extension_identifiers",
            "max_items",
            "categories",
            "tags",
        ],
        required_keys=[],
        description=(
            "Searches the Visual Studio Code Marketplace for extension adoption, "
            "publisher, install, rating, category, and tag signals."
        ),
    ),
    "figma_community": AdapterMetadata(
        name="figma_community",
        config_keys=[
            "queries",
            "tags",
            "sort",
            "include_plugins",
            "include_files",
            "max_items",
        ],
        required_keys=[],
        description=(
            "Searches Figma Community for plugin and file marketplace adoption, "
            "creator, like, duplicate, category, and tag signals."
        ),
    ),
    "terraform_registry": AdapterMetadata(
        name="terraform_registry",
        config_keys=["base_url", "queries", "module_queries", "provider_namespaces", "namespaces"],
        required_keys=[],
        description="Searches the Terraform Registry for infrastructure module and provider adoption signals.",
    ),
    "go_packages": AdapterMetadata(
        name="go_packages",
        config_keys=["queries", "max_results", "min_imported_by", "include_stdlib"],
        required_keys=[],
        description="Searches pkg.go.dev for Go package and module discovery signals.",
    ),
    "kubernetes_keps": AdapterMetadata(
        name="kubernetes_keps",
        config_keys=[
            "areas",
            "stages",
            "max_results",
            "github_token",
            "token",
            "token_env",
            "include_archived",
        ],
        required_keys=[],
        description="Fetches Kubernetes Enhancement Proposal roadmap metadata from GitHub.",
    ),
    "apis_guru": AdapterMetadata(
        name="apis_guru",
        config_keys=[
            "base_url",
            "queries",
            "providers",
            "preferred_versions_only",
            "categories",
        ],
        required_keys=[],
        description="Fetches APIs.guru OpenAPI Directory catalog signals for public API discovery.",
    ),
    "federal_register_healthcare": AdapterMetadata(
        name="federal_register_healthcare",
        config_keys=[
            "agencies",
            "topics",
            "search_terms",
            "document_types",
            "max_age_days",
            "base_url",
        ],
        required_keys=[],
        description=(
            "Fetches Federal Register healthcare rules, proposed rules, notices, "
            "and guidance-like regulatory change signals."
        ),
    ),
    "a2a_spec": AdapterMetadata(
        name="a2a_spec",
        config_keys=[
            "spec_urls",
            "local_paths",
            "sections",
            "keywords",
            "max_items",
            "include_examples",
        ],
        required_keys=[],
        description=(
            "Reads Agent-to-Agent specification Markdown, text, and JSON snapshots "
            "as protocol capability, lifecycle, transport, security, and interoperability signals."
        ),
    ),
}


def _discover_adapters() -> dict[str, type[SourceAdapter]]:
    """Discover adapters via entry_points, falling back to built-in imports."""
    adapters: dict[str, type[SourceAdapter]] = {}
    eps = []

    # Try entry_points first
    try:
        eps = importlib.metadata.entry_points(group="max.adapters")
        for ep in eps:
            try:
                cls = ep.load()
                if isinstance(cls, type) and issubclass(cls, SourceAdapter):
                    adapters[ep.name] = cls
                else:
                    logger.warning("Entry point '%s' is not a SourceAdapter subclass", ep.name)
            except Exception:
                logger.warning("Failed to load adapter entry_point '%s'", ep.name, exc_info=True)
    except Exception:
        logger.debug("entry_points discovery unavailable", exc_info=True)

    # Fallback: if no entry_points found, load built-ins directly. In dev
    # worktrees, installed package metadata can lag behind source, so merge
    # missing built-ins when entry points came from an installed distribution.
    if not adapters:
        _load_builtin_adapters(adapters, _BUILTIN_ADAPTERS)
    elif _has_distribution_entry_points(eps):
        missing = {
            name: target
            for name, target in _BUILTIN_ADAPTERS.items()
            if name not in adapters
        }
        _load_builtin_adapters(adapters, missing)

    return adapters


def _load_builtin_adapters(
    adapters: dict[str, type[SourceAdapter]],
    builtins: dict[str, str],
) -> None:
    for name, target in builtins.items():
        module_path, cls_name = target.rsplit(":", 1)
        try:
            mod = importlib.import_module(module_path)
            cls = getattr(mod, cls_name)
            adapters[name] = cls
        except Exception:
            logger.warning("Failed to load built-in adapter '%s'", name, exc_info=True)


def _has_distribution_entry_points(entry_points: object) -> bool:
    return any(getattr(ep, "dist", None) is not None for ep in entry_points)


def _filter_adapters(
    adapters: dict[str, type[SourceAdapter]],
) -> dict[str, type[SourceAdapter]]:
    """Apply include/exclude config filters."""
    from max.config import MAX_ADAPTERS, MAX_ADAPTERS_EXCLUDE

    if MAX_ADAPTERS != "all":
        enabled = {n.strip() for n in MAX_ADAPTERS.split(",") if n.strip()}
        adapters = {k: v for k, v in adapters.items() if k in enabled}

    if MAX_ADAPTERS_EXCLUDE:
        excluded = {n.strip() for n in MAX_ADAPTERS_EXCLUDE.split(",") if n.strip()}
        adapters = {k: v for k, v in adapters.items() if k not in excluded}

    return adapters


# Lazy-initialized cache
_cache: dict[str, type[SourceAdapter]] | None = None


def _get_registry() -> dict[str, type[SourceAdapter]]:
    global _cache  # noqa: PLW0603
    if _cache is None:
        _cache = _filter_adapters(_discover_adapters())
    return _cache


def get_adapter(name: str) -> SourceAdapter:
    """Get a single adapter by name."""
    registry = _get_registry()
    cls = registry.get(name)
    if cls is None:
        raise KeyError(f"Unknown adapter: {name}. Available: {list(registry)}")
    return cls()


def list_adapters() -> list[str]:
    """List names of all available adapters."""
    return list(_get_registry())


def _metadata_from_class(name: str, cls: type[SourceAdapter]) -> AdapterMetadata:
    """Return registry metadata for an adapter class."""
    builtin = _BUILTIN_ADAPTER_METADATA.get(name)
    if builtin is not None:
        return builtin

    description = getattr(cls, "description", None)
    if not isinstance(description, str) or not description.strip():
        description = (cls.__doc__ or "").strip().splitlines()[0] if cls.__doc__ else ""

    config_keys = getattr(cls, "config_keys", getattr(cls, "supported_config_keys", []))
    required_keys = getattr(cls, "required_keys", getattr(cls, "required_config_keys", []))

    return AdapterMetadata(
        name=name,
        config_keys=list(config_keys or []),
        required_keys=list(required_keys or []),
        description=description,
    )


def get_adapter_metadata() -> dict[str, AdapterMetadata]:
    """Return supported config keys, required keys, and descriptions for adapters."""
    return {
        name: _metadata_from_class(name, cls)
        for name, cls in _get_registry().items()
    }


def list_adapter_metadata() -> list[AdapterMetadata]:
    """Return adapter metadata as a sorted list."""
    return sorted(get_adapter_metadata().values(), key=lambda item: item.name)


def get_all_adapters(
    source_configs: list | None = None,
) -> list[SourceAdapter]:
    """Instantiate and return adapters.

    When *source_configs* is ``None``, returns all discovered adapters with
    default configuration (backward compatible).

    When a list of ``SourceConfig`` objects (or dicts with ``adapter``,
    ``enabled``, ``params`` keys) is provided, instantiates only the listed
    adapters with their per-profile configuration.
    """
    registry = _get_registry()

    if source_configs is None:
        return [cls() for cls in registry.values()]

    adapters: list[SourceAdapter] = []
    for sc in source_configs:
        # Accept both SourceConfig objects and plain dicts
        adapter_name = sc.adapter if hasattr(sc, "adapter") else sc.get("adapter", "")
        enabled = sc.enabled if hasattr(sc, "enabled") else sc.get("enabled", True)
        if hasattr(sc, "normalized_params"):
            params = sc.normalized_params
        elif hasattr(sc, "params"):
            params = sc.params
        else:
            params = sc.get("params", {})

        if not enabled:
            continue
        cls = registry.get(adapter_name)
        if cls is None:
            logger.warning("Profile references unknown adapter: %s", adapter_name)
            continue
        adapters.append(cls(config=params))
    return adapters


def reload_registry() -> None:
    """Force re-discovery. Useful for testing."""
    global _cache  # noqa: PLW0603
    _cache = None
