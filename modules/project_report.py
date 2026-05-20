"""Generate holistic project documentation (one AI call per repo)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from modules import project_report_helper as ph
from modules.ai_client_helper import AIEndpointError, chat_json_validated
from modules.common_helper import (
    CompletionResult,
    PROJECT_ROOT,
    RepoResult,
    is_month_complete,
    load_json,
    parse_repo_url,
    read_text_file,
    resolve_github_current_state,
    resolve_path,
    safe_filename,
    utc_now_iso,
)
from modules.report_paths_helper import (
    cleanup_stale_current_files,
    has_final_monthly,
    project_report_basename,
    remove_current_if_exists,
    repo_dir_name,
    report_current_path,
    report_final_path,
)
from modules.report_period_helper import months_with_commits

logger = logging.getLogger(__name__)


def _rollback_created(path: Path | None) -> None:
    if path and path.exists():
        path.unlink()
        logger.warning("Rollback: removed generated report %s", path)


class ProjectReportGenerator:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.state_dir = resolve_github_current_state(config)
        paths = config.get("paths") or {}
        self.output_root = resolve_path(str(paths.get("project_report", "project_report")), create=True)
        self.monthly_root = resolve_path(str(paths.get("monthly_report", "monthly_report")), create=True)
        pt = (config.get("prompts_and_templates") or {}).get("project_report") or {}
        self.prompt_path = PROJECT_ROOT / str(pt.get("prompt", "prompts/project_report.txt")).lstrip("/")

    def run(
        self,
        *,
        repo_urls: list[str] | None = None,
        refresh: bool = False,
    ) -> CompletionResult:
        """
        Generate project documentation.

        repo_urls: subset to process (default: all github_repos).
        refresh: if True, rewrite even when a final project file already exists
            (used after a new final monthly report was created).
        """
        result = CompletionResult(ok=True)
        targets = repo_urls if repo_urls is not None else list(self.config.get("github_repos") or [])
        for repo_url in targets:
            try:
                art = self._run_repo(repo_url, refresh=refresh)
                if art is None:
                    result.add_repo(
                        RepoResult(
                            url=repo_url,
                            ok=True,
                            artifacts=[],
                            error=None,
                        )
                    )
                else:
                    result.add_repo(RepoResult(url=repo_url, ok=True, artifacts=[art]))
            except AIEndpointError as exc:
                logger.warning(
                    "Project report aborted for %s due to AI endpoint error: %s",
                    repo_url,
                    exc,
                )
                result.add_repo(RepoResult(url=repo_url, ok=False, error=str(exc)))
            except Exception as exc:
                logger.exception("Project report failed for %s", repo_url)
                result.add_repo(RepoResult(url=repo_url, ok=False, error=str(exc)))
        return result

    def _run_repo(self, repo_url: str, *, refresh: bool = False) -> str | None:
        state_path = self.state_dir / safe_filename(repo_url)
        if not state_path.exists():
            raise FileNotFoundError(f"Missing cache {state_path}; run sync first")
        state = load_json(state_path)
        owner, name = parse_repo_url(repo_url)
        display = f"{owner}/{name}"
        repo_name = repo_dir_name(repo_url)
        out_dir = self.output_root / repo_name
        out_dir.mkdir(parents=True, exist_ok=True)

        monthly_dir = self.monthly_root / repo_name
        if not has_final_monthly(monthly_dir):
            logger.info(
                "Skip project for %s (no final monthly report yet; need completed month)",
                repo_name,
            )
            return None

        months = months_with_commits(state.get("commits") or [])
        has_open_month = any(not is_month_complete(y, m) for y, m in months) if months else True
        base = project_report_basename(repo_url)
        final_path = report_final_path(out_dir, base)
        current_path = report_current_path(out_dir, base)
        if not refresh and not has_open_month and final_path.exists():
            logger.info("Skip existing final project doc for %s", repo_name)
            return str(final_path)
        if has_open_month:
            remove_current_if_exists(out_dir, base)
        target = final_path if not has_open_month else current_path

        monthlies = self._collect_monthlies(monthly_dir)
        cache_summary = self._cache_summary(state)
        system = read_text_file(self.prompt_path)
        payload = {
            "repo_url": repo_url,
            "repo_display_name": display,
            "cache_summary": cache_summary,
            "monthly_reports": monthlies,
            "project_remark": state.get("project_remark"),
            "json_schema": ph.PROJECT_SCHEMA,
        }
        user_msg = (
            "Return a single JSON object matching the schema. Data:\n"
            + json.dumps(payload, indent=2, ensure_ascii=False)
        )
        try:
            data = chat_json_validated(
                self.config,
                system_prompt=system + "\n\nOutput ONLY valid JSON matching the provided schema.",
                user_payload=user_msg,
                debug_name=f"project_{repo_name}",
                validate=lambda d: ph.validate_project(d, cache_summary),
            )
            data["development_activity_summary"] = cache_summary
            md = ph.render_project_markdown(
                data,
                repo_display=display,
                repo_url=repo_url,
                generated_at=utc_now_iso(),
            )
            target.write_text(md, encoding="utf-8")
            logger.info("Wrote %s", target)
            if not has_open_month:
                remove_current_if_exists(out_dir, base)
            cleanup_stale_current_files(out_dir)
            return str(target)
        except Exception:
            _rollback_created(target)
            raise

    def _collect_monthlies(self, monthly_dir: Path) -> list[dict[str, str]]:
        if not monthly_dir.is_dir():
            return []
        items = []
        for path in sorted(monthly_dir.glob("*.md")):
            if path.name.endswith("_current.md"):
                continue
            items.append({"path": str(path), "content": path.read_text(encoding="utf-8")})
        return items

    def _cache_summary(self, state: dict[str, Any]) -> dict[str, int]:
        issues = state.get("issues") or []
        branches = state.get("branches") or []
        return {
            "commits_total": len(state.get("commits") or []),
            "issues_open": sum(1 for i in issues if i.get("state") == "open"),
            "issues_closed": sum(1 for i in issues if i.get("state") == "closed"),
            "branches_open": sum(1 for b in branches if b.get("status") == "open"),
            "branches_closed": sum(1 for b in branches if b.get("status") == "closed"),
        }
