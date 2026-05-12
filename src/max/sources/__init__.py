"""Source adapters."""

from max.sources.bitbucket_pull_requests import BitbucketPullRequestsAdapter
from max.sources.crates_io import CratesIoAdapter
from max.sources.dev_to import DevToAdapter
from max.sources.hackernews_jobs import HackerNewsJobsAdapter
from max.sources.indie_hackers import IndieHackersAdapter
from max.sources.maven_central import MavenCentralAdapter
from max.sources.packagist import PackagistAdapter
from max.sources.stackoverflow import StackOverflowAdapter

__all__ = [
    "BitbucketPullRequestsAdapter",
    "CratesIoAdapter",
    "DevToAdapter",
    "HackerNewsJobsAdapter",
    "IndieHackersAdapter",
    "MavenCentralAdapter",
    "PackagistAdapter",
    "StackOverflowAdapter",
]
