"""Sequential report pipeline: weekly → monthly → project."""

from __future__ import annotations

import logging
from typing import Any

from modules.common_helper import CompletionResult, RepoResult, resolve_path
from modules.monthly_report import MonthlyReportGenerator
from modules.project_report import ProjectReportGenerator
from modules.report_paths_helper import has_final_monthly, repo_dir_name
from modules.weekly_report import WeeklyReportGenerator

logger = logging.getLogger(__name__)


def merge_completion_results(*results: CompletionResult) -> CompletionResult:
    merged = CompletionResult(ok=True)
    for result in results:
        for repo in result.repos:
            merged.add_repo(repo)
        merged.errors.extend(result.errors)
    return merged


def _repos_with_new_final_monthlies(monthly_result: CompletionResult) -> set[str]:
    """Repo URLs that received at least one new non-draft monthly report this run."""
    urls: set[str] = set()
    for repo in monthly_result.repos:
        if not repo.ok:
            continue
        for path in repo.artifacts:
            if path.endswith(".md") and not path.endswith("_current.md"):
                urls.add(repo.url)
                break
    return urls


def run_report_pipeline(config: dict[str, Any]) -> CompletionResult:
    """
    Run report phases in order for all repos in config:
    1. Weekly — missing weeks only (existing finals skipped).
    2. Monthly — after weeklies exist for that month.
    3. Project — only for repos where a final (non-_current) monthly was created in step 2.
    """
    logger.info("Report pipeline: weekly (missing weeks)")
    weekly_result = WeeklyReportGenerator(config).run()
    if not weekly_result.ok:
        logger.warning(
            "Report pipeline stopped after weekly due to errors (AI endpoint or validation). "
            "No monthly/project generation this run."
        )
        return weekly_result

    logger.info("Report pipeline: monthly")
    monthly_result = MonthlyReportGenerator(config).run()
    if not monthly_result.ok:
        logger.warning(
            "Report pipeline stopped after monthly due to errors (AI endpoint or validation). "
            "No project generation this run."
        )
        return merge_completion_results(weekly_result, monthly_result)

    trigger_urls = _repos_with_new_final_monthlies(monthly_result)
    if not trigger_urls:
        logger.info(
            "Report pipeline: skip project (no new final monthly reports in this run)"
        )
        return merge_completion_results(weekly_result, monthly_result)

    logger.info(
        "Report pipeline: project for %d repo(s) with new final monthly report(s)",
        len(trigger_urls),
    )
    paths = config.get("paths") or {}
    monthly_root = resolve_path(str(paths.get("monthly_report", "monthly_report")))
    eligible = [
        url
        for url in config.get("github_repos") or []
        if url in trigger_urls and has_final_monthly(monthly_root / repo_dir_name(url))
    ]
    project_result = ProjectReportGenerator(config).run(
        repo_urls=eligible,
        refresh=True,
    )
    return merge_completion_results(weekly_result, monthly_result, project_result)
