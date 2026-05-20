"""Sync GitHub repository state into cumulative JSON snapshots."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from modules import github_handler_helper as gh
from modules.common_helper import (
    CompletionResult,
    RepoResult,
    load_json,
    parse_repo_url,
    resolve_github_current_state,
    safe_filename,
    save_json_atomic,
    utc_now_iso,
)

logger = logging.getLogger(__name__)


class GitHubHandler:
    """Fetch and merge GitHub data into per-repo JSON under github_current_state."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.state_dir = resolve_github_current_state(config)
        self.remark_name = (config.get("paths") or {}).get(
            "project_remark_and_log_file_name", "project_remark.txt"
        )

    def sync_current_state(self) -> CompletionResult:
        result = CompletionResult(ok=True)
        token = gh.github_token(self.config)
        repos = self.config.get("github_repos") or []
        if not repos:
            result.ok = False
            result.errors.append("github_repos is empty")
            return result

        for repo_url in repos:
            try:
                artifacts = self._sync_one(repo_url, token)
                result.add_repo(RepoResult(url=repo_url, ok=True, artifacts=artifacts))
            except Exception as exc:
                logger.exception("Sync failed for %s", repo_url)
                result.add_repo(RepoResult(url=repo_url, ok=False, error=str(exc)))
        return result

    def _sync_one(self, repo_url: str, token: str | None) -> list[str]:
        owner, name = parse_repo_url(repo_url)
        path = self.state_dir / safe_filename(repo_url)
        existing = load_json(path) if path.exists() else {}
        now = utc_now_iso()

        commits = gh.fetch_all_commits(owner, name, token)
        issues = gh.fetch_all_issues(owner, name, token)
        branch_names = gh.fetch_branch_names(owner, name, token)
        remark = gh.fetch_project_remark(owner, name, self.remark_name, token)

        merged = {
            "schema_version": 1,
            "repo_url": repo_url,
            "owner": owner,
            "name": name,
            "sync": {
                "first_sync_at": (existing.get("sync") or {}).get("first_sync_at") or now,
                "last_sync_at": now,
                "last_commit_sha": commits[-1]["sha"] if commits else None,
            },
            "commits": gh.merge_commits(existing.get("commits") or [], commits),
            "issues": gh.merge_issues(existing.get("issues") or [], issues),
            "branches": gh.merge_branches(existing.get("branches") or [], branch_names),
            "project_remark": remark,
        }
        save_json_atomic(path, merged)
        logger.info("Wrote state %s (%s commits)", path.name, len(merged["commits"]))
        return [str(path)]

    def state_path_for(self, repo_url: str) -> Path:
        return self.state_dir / safe_filename(repo_url)
