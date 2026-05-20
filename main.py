#!/usr/bin/env python3
"""github_repo_report — sync GitHub state and generate weekly/monthly/project reports."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from modules.common_helper import CompletionResult, load_config, resolve_path
from modules.github_handler import GitHubHandler
from modules.monthly_report import MonthlyReportGenerator
from modules.project_report import ProjectReportGenerator
from modules.report_orchestrator import run_report_pipeline
from modules.report_paths_helper import has_final_monthly, repo_dir_name
from modules.weekly_report import WeeklyReportGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)


def _exit_from_result(result: CompletionResult) -> int:
    for repo in result.repos:
        status = "OK" if repo.ok else "FAIL"
        arts = ", ".join(repo.artifacts) if repo.artifacts else "-"
        logging.info("%s %s artifacts=[%s]", status, repo.url, arts)
        if repo.error:
            logging.error("  %s", repo.error)
    for err in result.errors:
        logging.error(err)
    return 0 if result.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GitHub repo reporting pipeline")
    parser.add_argument(
        "command",
        nargs="?",
        default="reports",
        choices=["sync", "weekly", "monthly", "project", "reports", "all"],
        help=(
            "sync: GitHub cache | weekly/monthly/project: single phase | "
            "reports: weekly then monthly then project (if new final monthly) | "
            "all: sync + reports (default: reports)"
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parent / "config.json",
        help="Path to config.json",
    )
    args = parser.parse_args(argv)
    config = load_config(args.config)

    if args.command in ("sync", "all"):
        result = GitHubHandler(config).sync_current_state()
        if not result.ok:
            return _exit_from_result(result)

    if args.command == "weekly":
        return _exit_from_result(WeeklyReportGenerator(config).run())

    if args.command == "monthly":
        return _exit_from_result(MonthlyReportGenerator(config).run())

    if args.command == "project":
        paths = config.get("paths") or {}
        monthly_root = resolve_path(str(paths.get("monthly_report", "monthly_report")))
        eligible = [
            url
            for url in config.get("github_repos") or []
            if has_final_monthly(monthly_root / repo_dir_name(url))
        ]
        if not eligible:
            logging.warning("No repos with a final monthly report; run monthly first")
            return 1
        return _exit_from_result(
            ProjectReportGenerator(config).run(repo_urls=eligible, refresh=False)
        )

    if args.command in ("reports", "all"):
        return _exit_from_result(run_report_pipeline(config))

    return 0


if __name__ == "__main__":
    sys.exit(main())
