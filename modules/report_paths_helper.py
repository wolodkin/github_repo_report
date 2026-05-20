"""Report file paths, naming, and draft cleanup."""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path

from modules.common_helper import parse_date, parse_repo_url

logger = logging.getLogger(__name__)


def repo_dir_name(repo_url: str) -> str:
    """Subfolder name: repository name only (e.g. de_nbi, BITS)."""
    _, name = parse_repo_url(repo_url)
    return name


def commit_month_for_week(commits_in_week: list[dict]) -> tuple[int, int]:
    """YYYY-MM from commits in the ISO week; majority month, tie = earliest commit month."""
    if not commits_in_week:
        raise ValueError("commits_in_week must not be empty")
    counter: Counter[tuple[int, int]] = Counter()
    earliest_date = None
    earliest_month: tuple[int, int] | None = None
    for commit in commits_in_week:
        d = parse_date(commit.get("date", ""))
        ym = (d.year, d.month)
        counter[ym] += 1
        if earliest_date is None or d < earliest_date:
            earliest_date = d
            earliest_month = ym
    max_count = max(counter.values())
    leaders = [ym for ym, count in counter.items() if count == max_count]
    if len(leaders) == 1:
        return leaders[0]
    assert earliest_month is not None
    return earliest_month


def weekly_report_basename(iso_week: str, commits_in_week: list[dict]) -> str:
    """e.g. 2026-05-week_20 from ISO week label and commits in that week."""
    _year_label, week_s = iso_week.split("-W")
    week_num = int(week_s)
    year, month = commit_month_for_week(commits_in_week)
    return f"{year}-{month:02d}-week_{week_num}"


def monthly_report_basename(year: int, month: int) -> str:
    return f"{year}-{month:02d}"


def project_report_basename(repo_url: str) -> str:
    return repo_dir_name(repo_url)


def report_final_path(out_dir: Path, basename: str) -> Path:
    return out_dir / f"{basename}.md"


def report_current_path(out_dir: Path, basename: str) -> Path:
    return out_dir / f"{basename}_current.md"


def remove_current_if_exists(out_dir: Path, basename: str) -> None:
    current = report_current_path(out_dir, basename)
    if current.exists():
        current.unlink()
        logger.debug("Removed draft %s", current.name)


def is_final_report_path(path: Path | str) -> bool:
    name = Path(path).name
    return name.endswith(".md") and not name.endswith("_current.md")


def has_final_monthly(monthly_dir: Path) -> bool:
    """True if the repo has at least one completed-month report (YYYY-MM.md, not _current)."""
    if not monthly_dir.is_dir():
        return False
    return any(is_final_report_path(p) for p in monthly_dir.glob("*.md"))


def cleanup_stale_current_files(directory: Path) -> None:
    """Remove *_current.md when the matching final report already exists."""
    if not directory.is_dir():
        return
    for current in directory.glob("*_current.md"):
        final_name = current.name[: -len("_current.md")] + ".md"
        final = directory / final_name
        if final.is_file():
            current.unlink()
            logger.info("Removed stale draft %s (final exists)", current.name)
