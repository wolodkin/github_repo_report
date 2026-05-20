"""Generate monthly reports (one AI call per month, weeklies attached)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from modules import monthly_report_helper as mh
from modules.ai_client_helper import AIEndpointError, chat_json_validated
from modules.common_helper import (
    CompletionResult,
    PROJECT_ROOT,
    RepoResult,
    is_month_complete,
    load_json,
    month_label,
    month_name,
    parse_repo_url,
    read_text_file,
    resolve_github_current_state,
    resolve_path,
    safe_filename,
)
from modules.report_paths_helper import (
    cleanup_stale_current_files,
    monthly_report_basename,
    remove_current_if_exists,
    repo_dir_name,
    report_current_path,
    report_final_path,
    weekly_report_basename,
)
from modules.report_period_helper import commits_in_week
from modules.report_period_helper import (
    branch_buckets_for_month,
    commits_in_month,
    issue_buckets_for_month,
    months_with_commits,
    weeks_in_month,
)

logger = logging.getLogger(__name__)


def _rollback_created(paths: list[Path]) -> None:
    for path in reversed(paths):
        if path.exists():
            path.unlink()
            logger.warning("Rollback: removed generated report %s", path)


class MonthlyReportGenerator:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.state_dir = resolve_github_current_state(config)
        paths = config.get("paths") or {}
        self.output_root = resolve_path(str(paths.get("monthly_report", "monthly_report")), create=True)
        self.weekly_root = resolve_path(str(paths.get("weekly_report", "weekly_report")), create=True)
        pt = (config.get("prompts_and_templates") or {}).get("monthly_report") or {}
        self.prompt_path = PROJECT_ROOT / str(pt.get("prompt", "prompts/monthly_report.txt")).lstrip("/")

    def run(self) -> CompletionResult:
        result = CompletionResult(ok=True)
        for repo_url in self.config.get("github_repos") or []:
            try:
                arts = self._run_repo(repo_url)
                result.add_repo(RepoResult(url=repo_url, ok=True, artifacts=arts))
            except AIEndpointError as exc:
                logger.warning(
                    "Monthly reports aborted for %s due to AI endpoint error: %s",
                    repo_url,
                    exc,
                )
                result.add_repo(RepoResult(url=repo_url, ok=False, error=str(exc)))
            except Exception as exc:
                logger.exception("Monthly reports failed for %s", repo_url)
                result.add_repo(RepoResult(url=repo_url, ok=False, error=str(exc)))
        return result

    def _run_repo(self, repo_url: str) -> list[str]:
        state_path = self.state_dir / safe_filename(repo_url)
        if not state_path.exists():
            raise FileNotFoundError(f"Missing cache {state_path}; run sync first")
        state = load_json(state_path)
        owner, name = parse_repo_url(repo_url)
        display = f"{owner}/{name}"
        repo_name = repo_dir_name(repo_url)
        weekly_dir = self.weekly_root / repo_name
        out_dir = self.output_root / repo_name
        out_dir.mkdir(parents=True, exist_ok=True)
        system = read_text_file(self.prompt_path)
        artifacts: list[str] = []
        created_paths: list[Path] = []
        commits = state.get("commits") or []
        try:
            for year, month in months_with_commits(commits):
                ml = month_label(year, month)
                base = monthly_report_basename(year, month)
                complete = is_month_complete(year, month)
                final_path = report_final_path(out_dir, base)
                current_path = report_current_path(out_dir, base)
                if complete and final_path.exists():
                    logger.info("Skip existing final %s", final_path.name)
                    continue

                weeklies = self._collect_weeklies(weekly_dir, commits, year, month)
                if not weeklies:
                    logger.warning("No weekly files for %s %s; skipping monthly", repo_name, ml)
                    continue

                if not complete:
                    remove_current_if_exists(out_dir, base)
                target = final_path if complete else current_path

                month_commits = commits_in_month(commits, year, month)
                payload = {
                    "repo_url": repo_url,
                    "repo_display_name": display,
                    "month": ml,
                    "month_name": month_name(year, month),
                    "year": year,
                    "weekly_reports": weeklies,
                    "commit_count": len(month_commits),
                    "github_trends": {
                        "issues": issue_buckets_for_month(state.get("issues") or [], year, month),
                        "branches": branch_buckets_for_month(state.get("branches") or [], year, month),
                    },
                    "json_schema": mh.MONTHLY_SCHEMA,
                }
                user_msg = (
                    "Return a single JSON object matching the schema. Data:\n"
                    + json.dumps(payload, indent=2, ensure_ascii=False)
                )
                trends = payload["github_trends"]
                data = chat_json_validated(
                    self.config,
                    system_prompt=system + "\n\nOutput ONLY valid JSON matching the provided schema.",
                    user_payload=user_msg,
                    debug_name=f"monthly_{repo_name}_{base}",
                    validate=mh.validate_monthly,
                )
                data["github_trends"] = trends
                data.setdefault("metrics", {})["commits"] = len(month_commits)
                data["metrics"]["weekly_reports_used"] = len(weeklies)
                md = mh.render_monthly_markdown(
                    data,
                    repo_display=display,
                    month_name=month_name(year, month),
                    year=year,
                )
                target.write_text(md, encoding="utf-8")
                created_paths.append(target)
                logger.info("Wrote %s", target)
                artifacts.append(str(target))
                if complete:
                    remove_current_if_exists(out_dir, base)
            cleanup_stale_current_files(out_dir)
            return artifacts
        except Exception:
            _rollback_created(created_paths)
            raise

    def _collect_weeklies(
        self,
        weekly_dir: Path,
        commits: list[dict],
        year: int,
        month: int,
    ) -> list[dict[str, str]]:
        if not weekly_dir.is_dir():
            return []
        out: list[dict[str, str]] = []
        for iso_week in weeks_in_month(commits, year, month):
            week_commits = commits_in_week(commits, iso_week)
            if not week_commits:
                continue
            base = weekly_report_basename(iso_week, week_commits)
            for path in (
                report_final_path(weekly_dir, base),
                report_current_path(weekly_dir, base),
            ):
                if path.is_file():
                    out.append(
                        {
                            "iso_week": iso_week,
                            "path": str(path),
                            "content": path.read_text(encoding="utf-8"),
                        }
                    )
                    break
        return out
