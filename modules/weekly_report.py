"""Generate weekly reports from cache JSON via one AI call per week."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from modules import weekly_report_helper as wh
from modules.ai_client_helper import AIEndpointError, chat_json_validated
from modules.common_helper import (
    CompletionResult,
    PROJECT_ROOT,
    RepoResult,
    iso_week_bounds,
    is_week_complete,
    load_json,
    parse_repo_url,
    read_text_file,
    resolve_github_current_state,
    resolve_path,
    safe_filename,
)
from modules.report_paths_helper import (
    cleanup_stale_current_files,
    remove_current_if_exists,
    repo_dir_name,
    report_current_path,
    report_final_path,
    weekly_report_basename,
)
from modules.report_period_helper import (
    branch_buckets_for_week,
    commits_in_week,
    issue_buckets_for_week,
    weeks_with_commits,
)

logger = logging.getLogger(__name__)


def _rollback_created(paths: list[Path]) -> None:
    for path in reversed(paths):
        if path.exists():
            path.unlink()
            logger.warning("Rollback: removed generated report %s", path)


class WeeklyReportGenerator:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.state_dir = resolve_github_current_state(config)
        paths = config.get("paths") or {}
        self.output_root = resolve_path(str(paths.get("weekly_report", "weekly_report")), create=True)
        pt = (config.get("prompts_and_templates") or {}).get("weekly_report") or {}
        self.prompt_path = PROJECT_ROOT / str(pt.get("prompt", "prompts/weekly_report.txt")).lstrip("/")

    def run(self) -> CompletionResult:
        result = CompletionResult(ok=True)
        for repo_url in self.config.get("github_repos") or []:
            try:
                arts = self._run_repo(repo_url)
                result.add_repo(RepoResult(url=repo_url, ok=True, artifacts=arts))
            except AIEndpointError as exc:
                logger.warning(
                    "Weekly reports aborted for %s due to AI endpoint error: %s",
                    repo_url,
                    exc,
                )
                result.add_repo(RepoResult(url=repo_url, ok=False, error=str(exc)))
            except Exception as exc:
                logger.exception("Weekly reports failed for %s", repo_url)
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
        out_dir = self.output_root / repo_name
        out_dir.mkdir(parents=True, exist_ok=True)
        system = read_text_file(self.prompt_path)
        artifacts: list[str] = []
        created_paths: list[Path] = []
        try:
            for iso_week in weeks_with_commits(state.get("commits") or []):
                week_commits = commits_in_week(state.get("commits") or [], iso_week)
                if not week_commits:
                    continue
                base = weekly_report_basename(iso_week, week_commits)
                complete = is_week_complete(iso_week)
                final_path = report_final_path(out_dir, base)
                current_path = report_current_path(out_dir, base)
                if complete and final_path.exists():
                    logger.info("Skip existing final %s", final_path.name)
                    continue
                if not complete:
                    remove_current_if_exists(out_dir, base)
                target = final_path if complete else current_path

                ib = issue_buckets_for_week(state.get("issues") or [], iso_week)
                bb = branch_buckets_for_week(state.get("branches") or [], iso_week)
                start, end = iso_week_bounds(iso_week)
                year = int(iso_week.split("-")[0])
                payload = {
                    "repo_url": repo_url,
                    "repo_display_name": display,
                    "iso_week": iso_week,
                    "week_start": start.isoformat(),
                    "week_end": end.isoformat(),
                    "commits": week_commits,
                    "issues": ib,
                    "branches": bb,
                    "project_remark": state.get("project_remark"),
                    "json_schema": wh.WEEKLY_SCHEMA,
                }
                user_msg = (
                    "Return a single JSON object matching the schema. Data:\n"
                    + json.dumps(payload, indent=2, ensure_ascii=False)
                )
                data = chat_json_validated(
                    self.config,
                    system_prompt=system + "\n\nOutput ONLY valid JSON matching the provided schema.",
                    user_payload=user_msg,
                    debug_name=f"weekly_{repo_name}_{base}",
                    validate=lambda d: wh.validate_weekly(d, had_commits=True),
                )
                ga = data.setdefault("github_activity", {})
                ga["issues"] = {
                    **ga.get("issues", {}),
                    "new": ib["counts"]["new"],
                    "open": ib["counts"]["open"],
                    "closed": ib["counts"]["closed"],
                    "notes": ga.get("issues", {}).get("notes", ""),
                }
                ga["branches"] = {
                    **ga.get("branches", {}),
                    "new": bb["counts"]["new"],
                    "open": bb["counts"]["open"],
                    "closed": bb["counts"]["closed"],
                    "notes": ga.get("branches", {}).get("notes", ""),
                }
                md = wh.render_weekly_markdown(
                    data,
                    repo_display=display,
                    iso_week=iso_week,
                    year=year,
                    week_start=start.isoformat(),
                    week_end=end.isoformat(),
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
